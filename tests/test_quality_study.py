import json

import httpx
import pytest

from atlas.errors import AtlasError
from atlas.providers import GroundedAnswer
from atlas.quality_study import StudyModel
from tests.test_provider import passage, tags


def model(reply, *, done=True, digest="b" * 64, requests=None):
    def handler(request):
        if request.url.path == "/api/tags":
            metadata = tags()
            metadata["models"][1]["digest"] = digest
            return httpx.Response(200, json=metadata)
        if requests is not None:
            requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "qwen3:1.7b",
                "done": done,
                "message": {"content": json.dumps(reply)},
                "prompt_eval_count": 10,
                "eval_count": 4,
            },
        )

    return StudyModel(transport=httpx.MockTransport(handler))


def test_rank_is_permutation_of_original_evidence_and_has_no_labels():
    requests = []
    first = passage()
    second = first.model_copy(update={"id": "chunk-2", "text": "Other evidence"})
    ranked, usage = model({"order": [1, 0]}, requests=requests).rank(
        "Which retry limit?", [first, second], "b" * 64
    )
    assert ranked == [second, first]
    payload = json.loads(requests[0]["messages"][1]["content"])
    assert set(payload) == {"question", "passages"}
    assert usage.output_tokens == 4
    assert "tools" not in requests[0]


@pytest.mark.parametrize("order", [[0, 0], [1], [-1, 0], [0, 2], [False, 1]])
def test_invalid_reranker_references_fail_without_fallback(order):
    with pytest.raises(AtlasError, match="invalid candidate"):
        model({"order": order}).rank(
            "question", [passage(), passage().model_copy(update={"id": "chunk-2"})], "b" * 64
        )


def test_empty_rank_skips_inference_and_changed_model_is_rejected():
    def forbidden(request):
        pytest.fail("No model call for empty candidate pool")

    assert (
        StudyModel(transport=httpx.MockTransport(forbidden)).rank("question", [], "b" * 64)[0] == []
    )
    with pytest.raises(AtlasError, match="identity changed"):
        model({"order": [0]}, digest="c" * 64).rank("question", [passage()], "b" * 64)
    with pytest.raises(AtlasError, match="invalid output"):
        model({"order": [0]}, done=False).rank("question", [passage()], "b" * 64)


def test_judge_records_model_categories_not_human_ratings_and_validates_counts():
    requests = []
    answer = GroundedAnswer(
        status="insufficient_evidence", claims=[], model="qwen3:1.7b", model_digest="b" * 64
    )
    reply = {
        "facts": ["missing"],
        "claims": [],
        "status_appropriate": False,
        "conflict_handling": "not_applicable",
    }
    judgment, _ = model(reply, requests=requests).judge(
        "question", ["expected fact"], True, answer, [], "b" * 64
    )
    properties = requests[0]["format"]["properties"]
    assert properties["facts"]["minItems"] == properties["facts"]["maxItems"] == 1
    assert properties["claims"]["minItems"] == properties["claims"]["maxItems"] == 0
    assert judgment.facts == ["missing"] and not judgment.status_appropriate
    assert "rating_reviewer" not in judgment.model_dump()
    with pytest.raises(AtlasError, match="rating counts"):
        model(reply).judge("question", [], False, answer, [], "b" * 64)


def test_reranker_bounds_and_untrusted_output_are_not_exposed():
    with pytest.raises(AtlasError, match="work bound"):
        model({}).rank("x" * 513, [], "b" * 64)
    with pytest.raises(AtlasError) as error:
        model({"secret": "PRIVATE_PROVIDER_OUTPUT"}).rank("question", [passage()], "b" * 64)
    assert "PRIVATE_PROVIDER_OUTPUT" not in str(error.value)
