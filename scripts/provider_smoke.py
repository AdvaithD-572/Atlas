"""Real local-model integration, using explicitly synthetic non-benchmark content."""

import json
from pathlib import Path
from time import perf_counter

from atlas.providers import OllamaProvider
from atlas.schemas import Passage


def main() -> None:
    provider = OllamaProvider()
    text = "The Atlas test server retries failed requests three times."
    passage = Passage(
        id="synthetic-passage",
        document_id="synthetic-document",
        source_key="smoke",
        version=1,
        ordinal=0,
        start=0,
        end=len(text),
        text=text,
    )
    started = perf_counter()
    embedding = provider.embed([text, "How many times does the server retry?"])
    embedded = perf_counter()
    answer = provider.generate(
        "How many times does the Atlas test server retry failed requests?", [passage]
    )
    assert answer.status == "answered" and answer.claims
    assert all(claim.text in text for claim in answer.claims)
    assert all(claim.citation_ids == [passage.id] for claim in answer.claims)
    abstention = provider.generate("What is the capital of a fictional planet?", [])
    assert abstention.status == "insufficient_evidence"
    report = {
        "scope": "synthetic local integration smoke; not a quality benchmark",
        "embedding_model": embedding.model,
        "embedding_digest": embedding.model_digest,
        "dimension": len(embedding.vectors[0]),
        "embedding_ms": round((embedded - started) * 1000, 2),
        "generation_model": answer.model,
        "generation_digest": answer.model_digest,
        "generation_ms": round((perf_counter() - embedded) * 1000, 2),
        "prompt_version": answer.prompt_version,
        "input_tokens": answer.input_tokens,
        "output_tokens": answer.output_tokens,
        "status": answer.status,
        "claims_validated": len(answer.claims),
        "empty_evidence_abstention": "passed",
        "provider_fee_usd": 0,
        "compute_cost_usd": None,
    }
    Path(".local/provider-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
