"""Real PostgreSQL, synthetic embedding fixtures; no model-quality benchmark."""

from pathlib import Path

import pytest

from atlas.errors import AtlasError
from atlas.postgres import db_connection
from atlas.providers import Embeddings
from atlas.retrieval import SearchRequest
from atlas.vector_retrieval import PostgresVectorService, reciprocal_rank_fusion
from tests.test_postgres import service  # noqa: F401


class SyntheticEmbeddingProvider:
    def __init__(self):
        self.digest = "a" * 64
        self.calls = 0
        self.on_call = None
        self.fail_on = None

    def embed(self, texts):
        self.calls += 1
        if self.on_call:
            self.on_call()
        if self.calls == self.fail_on:
            raise AtlasError("synthetic_failure", "Synthetic provider failure", 503)
        vectors = [[1.0, 0.0] if "rotation" in text.casefold() else [0.0, 1.0] for text in texts]
        return Embeddings(model="synthetic-test-v1", model_digest=self.digest, vectors=vectors)


@pytest.fixture
def vectors(service):  # noqa: F811
    # Apply the actual new migration in an isolated schema while parent wires version 2.
    with db_connection(service.dsn) as db:
        if (
            db.execute("SELECT to_regclass('chunk_embeddings') AS table_name").fetchone()[
                "table_name"
            ]
            is None
        ):
            db.execute(Path("atlas/pg_migrations/002_embeddings.sql").read_text())
    return PostgresVectorService(service, SyntheticEmbeddingProvider())


def test_rrf_rank_math_ties_and_duplicates():
    result = reciprocal_rank_fusion([["a", "b", "a"], ["b", "c"]], rank_constant=60, limit=3)
    assert [identifier for identifier, _ in result] == ["b", "a", "c"]
    assert result[0][1] == pytest.approx(1 / 62 + 1 / 61)
    assert reciprocal_rank_fusion([["z"], ["a"]]) == [("a", 1 / 61), ("z", 1 / 61)]
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([["a"]], rank_constant=0)


def test_vector_index_owner_isolation_and_metadata(vectors):
    docs = vectors.documents
    alice, _ = docs.put("alice", "guide", b"Token rotation guide", "text/plain")
    bob, _ = docs.put("bob", "private", b"Private rotation", "text/plain")
    with pytest.raises(AtlasError) as denied:
        vectors.index_document("alice", bob.id)
    assert denied.value.status == 404 and vectors.provider.calls == 0
    indexed = vectors.index_document("alice", alice.id)
    assert indexed.document_id == alice.id and indexed.document_version == 1
    assert indexed.chunk_count == 1 and indexed.model_digest == "a" * 64
    vectors.index_document("bob", bob.id)
    query = SearchRequest(question="rotation")
    result = vectors.search("alice", query)
    assert result.mode == "vector" and result.indexed_chunks == 1
    assert [p.document_id for p in result.passages] == [alice.id]
    assert not vectors.search("charlie", query).passages
    assert vectors.search("bob", query).passages[0].document_id == bob.id


def test_reindex_is_atomic_and_deletion_cascades(vectors):
    doc, _ = vectors.documents.put("alice", "guide", b"rotation", "text/plain")
    vectors.index_document("alice", doc.id)
    vectors.index_document("alice", doc.id)
    with db_connection(vectors.documents.dsn) as db:
        assert db.execute("SELECT count(*) AS n FROM chunk_embeddings").fetchone()["n"] == 1
    vectors.documents.delete("alice", doc.id)
    with db_connection(vectors.documents.dsn) as db:
        assert db.execute("SELECT count(*) AS n FROM chunk_embeddings").fetchone()["n"] == 0


def test_document_update_during_embedding_cannot_publish_stale_rows(vectors):
    doc, _ = vectors.documents.put("alice", "guide", b"rotation", "text/plain")
    vectors.provider.on_call = lambda: vectors.documents.put(
        "alice", "guide", b"new text", "text/plain"
    )
    with pytest.raises(AtlasError) as changed:
        vectors.index_document("alice", doc.id)
    assert changed.value.code == "evidence_changed"
    with db_connection(vectors.documents.dsn) as db:
        assert db.execute("SELECT count(*) AS n FROM chunk_embeddings").fetchone()["n"] == 0


def test_failed_later_batch_preserves_previous_complete_index(vectors):
    vectors.documents.settings.chunk_size = 64
    vectors.documents.settings.chunk_overlap = 0
    doc, _ = vectors.documents.put("alice", "guide", b"rotation " * 300, "text/plain")
    original = vectors.index_document("alice", doc.id)
    vectors.provider.fail_on = vectors.provider.calls + 2
    with pytest.raises(AtlasError):
        vectors.index_document("alice", doc.id)
    with db_connection(vectors.documents.dsn) as db:
        assert (
            db.execute("SELECT count(*) AS n FROM chunk_embeddings").fetchone()["n"]
            == original.chunk_count
        )


def test_changed_model_and_changed_document_are_excluded(vectors):
    doc, _ = vectors.documents.put("alice", "guide", b"rotation", "text/plain")
    vectors.index_document("alice", doc.id)
    vectors.provider.digest = "b" * 64
    result = vectors.search("alice", SearchRequest(question="rotation"))
    assert result.indexed_chunks == 0 and result.unindexed_chunks == 1 and not result.passages
    vectors.provider.digest = "a" * 64
    vectors.documents.put("alice", "guide", b"rotation changed", "text/plain")
    result = vectors.search("alice", SearchRequest(question="rotation"))
    assert not result.passages and result.unindexed_chunks == 1


def test_hybrid_uses_real_lexical_and_vector_rankings(vectors):
    first, _ = vectors.documents.put("alice", "guide", b"rotation guide", "text/plain")
    second, _ = vectors.documents.put("alice", "other", b"unrelated document", "text/plain")
    vectors.index_document("alice", first.id)
    vectors.index_document("alice", second.id)
    result = vectors.search("alice", SearchRequest(question="rotation"), mode="hybrid")
    assert result.mode == "hybrid" and result.rrf_rank_constant == 60
    assert result.passages[0].document_id == first.id
    assert len({p.id for p in result.passages}) == len(result.passages)


def test_index_batch_identity_must_not_change(vectors):
    vectors.documents.settings.chunk_size = 64
    vectors.documents.settings.chunk_overlap = 0
    doc, _ = vectors.documents.put("alice", "guide", b"rotation " * 300, "text/plain")

    def switch():
        if vectors.provider.calls == 2:
            vectors.provider.digest = "b" * 64

    vectors.provider.on_call = switch
    with pytest.raises(AtlasError) as changed:
        vectors.index_document("alice", doc.id)
    assert changed.value.code == "embedding_changed"
    with db_connection(vectors.documents.dsn) as db:
        assert db.execute("SELECT count(*) AS n FROM chunk_embeddings").fetchone()["n"] == 0


def test_vector_http_index_search_answer_and_owner_isolation(vectors):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from atlas.main import create_app
    from tests.test_questions import FakeGenerator

    settings = vectors.documents.settings.model_copy(
        update={
            "postgres_dsn": SecretStr(vectors.documents.dsn),
            "vector_enabled": True,
            "generation_enabled": True,
        }
    )
    app = create_app(settings)
    app.state.vectors = vectors
    app.state.provider = FakeGenerator()
    headers = {"Authorization": "Bearer test-only"}
    with TestClient(app) as client:
        modes = client.get("/v1/capabilities", headers=headers).json()["retrieval_modes"]
        assert modes == ["lexical", "vector", "hybrid"]
        doc = client.put(
            "/v1/documents/guide",
            content=b"Token rotation guide",
            headers={**headers, "Content-Type": "text/plain"},
        ).json()
        target = f"/v1/documents/{doc['id']}/vector-index"
        assert client.post(target).status_code == 401
        assert client.post(target, headers=headers).status_code == 200
        for mode in ("vector", "hybrid"):
            response = client.post(
                f"/v1/search?mode={mode}", headers=headers, json={"question": "rotation"}
            )
            assert response.status_code == 200
            assert response.json()["passages"][0]["document_id"] == doc["id"]
            response = client.post(
                f"/v1/answers?mode={mode}", headers=headers, json={"question": "rotation"}
            )
            assert response.status_code == 200
            assert response.json()["answer"]["status"] == "answered"
            assert response.json()["retrieval"]["mode"] == mode
            from atlas.evaluation import DatasetCase, ExperimentConfig, lexical_http_observer
            from tests.test_evaluation import row

            observer = lexical_http_observer(client, headers)
            config = ExperimentConfig(
                mode=mode,
                retrieval_version=response.json()["retrieval_version"],
                model_id="synthetic-test-v1",
                model_digest="a" * 64,
            )
            observation = observer(DatasetCase.model_validate(row(question="rotation")), config)
            assert observation.retrieved_passage_ids == [response.json()["passages"][0]["id"]]
            with pytest.raises(ValueError, match="identity"):
                observer(
                    DatasetCase.model_validate(row(question="rotation")),
                    config.model_copy(update={"model_digest": "b" * 64}),
                )
        assert (
            client.post(
                "/v1/search?mode=unknown", headers=headers, json={"question": "rotation"}
            ).status_code
            == 422
        )


def test_vector_limit_and_busy_fail_before_provider_work(vectors):
    vectors.documents.settings.chunk_size = 64
    vectors.documents.settings.chunk_overlap = 0
    doc, _ = vectors.documents.put("alice", "big", b"x" * (129 * 64), "text/plain")
    with pytest.raises(AtlasError) as failure:
        vectors.index_document("alice", doc.id)
    assert failure.value.code == "vector_index_limit" and vectors.provider.calls == 0
    vectors._index_slots.acquire()
    try:
        with pytest.raises(AtlasError) as failure:
            vectors.index_document("alice", doc.id)
        assert failure.value.code == "index_busy"
    finally:
        vectors._index_slots.release()
