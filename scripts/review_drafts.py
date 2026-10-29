"""Prepare source-bound AI-authored review drafts; never attest human review."""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

SOURCES = {
    "ops": "docs/operations.md",
    "provider": "docs/engineering/provider-evidence.md",
    "pg": "docs/engineering/postgres-evidence.md",
    "vector": "docs/engineering/vector-evidence.md",
    "eval": "docs/evaluation.md",
    "plan": "docs/engineering/implementation-plan.md",
    "frontend": "docs/engineering/frontend-evidence.md",
    "foundation": "docs/engineering/evaluation-evidence.md",
    "browser": "docs/engineering/browser-evidence.md",
    "deployment": "docs/engineering/deployment-evidence.md",
    "readme": "README.md",
    "state": "BUILD_STATE.md",
}

# Questions and evidence anchors were authored and critiqued by the same AI agent.
# Anchors match real documentation; whitespace may wrap across source lines.
FACTS = [
    (
        "ops",
        "Raw UTF-8 `text/plain` or `text/markdown`",
        "Which MIME types does the document PUT endpoint accept?",
    ),
    (
        "ops",
        "Per-process authenticated limit defaults to 120 requests/minute/principal",
        "What is the default authenticated request rate limit?",
    ),
    ("ops", "Storage lock wait is five seconds", "How long does the local storage lock wait last?"),
    ("ops", "upload read timeout ten seconds", "What is the upload read timeout?"),
    (
        "ops",
        "Upload keys: 1–120 characters, alphanumeric first",
        "What is the allowed length and first-character rule for an upload key?",
    ),
    (
        "ops",
        "Source spans are zero-based Unicode code point offsets",
        "What units and origin do source character spans use?",
    ),
    (
        "ops",
        "Removing a digest and restarting revokes access, not documents",
        "How is a local credential revoked, and are its documents removed?",
    ),
    (
        "ops",
        "Replacement removes prior text/chunks and invalidates previous citation IDs",
        "What happens to previous passages and citations when a document is replaced?",
    ),
    (
        "ops",
        "materializes only owner-authorized candidates (200 cap, explicit truncated flag)",
        "How many lexical candidates can be considered, and is truncation disclosed?",
    ),
    (
        "ops",
        "expects schema version 2",
        "Which PostgreSQL schema version does readiness expect in this snapshot?",
    ),
    (
        "ops",
        "At most 128 chunks are indexed per call",
        "What is the semantic indexing chunk limit per call?",
    ),
    (
        "ops",
        "Cloud models and non-loopback providers are rejected",
        "Can the configured model provider be a cloud or non-loopback endpoint?",
    ),
    (
        "ops",
        "Open `http://127.0.0.1:8080`",
        "Which loopback address serves the local container frontend?",
    ),
    (
        "ops",
        "The image runs as UID/GID 10001",
        "Which user and group IDs does the application image use?",
    ),
    (
        "ops",
        "The worker has no health probe",
        "Does this container profile provide a worker health probe?",
    ),
    (
        "provider",
        "Provider service fee is zero; local compute/electricity cost is unmeasured",
        "Which local-provider cost is zero and which remains unmeasured?",
    ),
    (
        "provider",
        "60-second overall HTTP deadline",
        "What overall deadline bounds one local-provider HTTP call?",
    ),
    (
        "provider",
        "2 MB output limit",
        "What response-size limit protects the local-provider boundary?",
    ),
    (
        "provider",
        "bounded two-slot concurrency",
        "How many concurrent requests can enter the local-provider boundary?",
    ),
    (
        "provider",
        "each claim must occur verbatim in every cited passage",
        "What exact-source condition must every generated claim meet?",
    ),
    ("pg", "Leases default to 30 seconds", "What is the default durable-ingestion lease duration?"),
    (
        "pg",
        "with at most three attempts",
        "What is the maximum ingestion processing attempt count?",
    ),
    (
        "pg",
        "20 active jobs per owner, 2,000 globally",
        "What are the per-owner and global active-job limits?",
    ),
    (
        "eval",
        "Official mode requires at least 100 cases",
        "How many cases does official evaluation mode require at minimum?",
    ),
    (
        "vector",
        "top 20 results from each baseline, score sum `1 / (60 + rank)` with one-based ranks",
        "Which rank depth and formula does hybrid reciprocal rank fusion use?",
    ),
]

PARAPHRASES = [
    "Can the ingestion endpoint consume a UTF-8 Markdown body, and under which content type?",
    (
        "How many authenticated calls can one identity make per minute in "
        "a single API process by default?"
    ),
    "How long may a request wait for the local database lock?",
    "When does a stalled upload-body read time out?",
    "What length and initial symbol constraints apply to my document's stable upload identifier?",
    "Are passage positions measured in bytes or Unicode characters, and do they start at zero?",
    "How do I invalidate an operator-issued token without deleting the owner's source material?",
    (
        "If I overwrite a source under its existing key, will its previous"
        " citation links still resolve?"
    ),
    (
        "How many authorized matches enter lexical ranking before its "
        "incomplete-results warning applies?"
    ),
    "What migration revision must the PostgreSQL database reach before the API considers it ready?",
    "What is the largest passage count accepted by one semantic-index operation?",
    "May inference requests leave loopback and use a remotely hosted model?",
    "Which local URL should I open after starting the packaged API?",
    "Under which numeric identity does the application run inside its container?",
    "Can I infer background-job progress from a configured worker health check?",
    "Does a zero model service charge mean machine operating costs were measured as zero?",
    "How much total time may one provider HTTP exchange consume?",
    "How large can a response from the local inference service grow before it is rejected?",
    "How many provider calls can be admitted simultaneously?",
    "Can a generated statement cite a passage that does not contain that statement exactly?",
]

# Each combined question requires two different documents; conjunctions are a
# deliberately simple development baseline, not a realistic multi-hop benchmark.
PAIRS = [
    (
        0,
        19,
        (
            "Which upload formats are accepted, and what source-containment "
            "rule applies to a generated claim?"
        ),
    ),
    (
        1,
        18,
        "What per-principal request limit and provider concurrency limit constrain query traffic?",
    ),
    (2, 16, "What are the documented storage-lock wait and provider HTTP deadline?"),
    (
        3,
        17,
        "Which time limit bounds reading an upload and which byte limit bounds provider output?",
    ),
    (4, 22, "What upload-key length rule and active-job quotas apply when submitting documents?"),
    (
        5,
        19,
        (
            "How are source spans measured, and how must generated claims "
            "relate to their cited passage text?"
        ),
    ),
    (6, 21, "How is an owner's token revoked, and what is the ingestion attempt limit?"),
    (
        7,
        20,
        (
            "What happens to old citations after replacement, and how long is "
            "the default worker lease?"
        ),
    ),
    (
        8,
        24,
        (
            "What lexical candidate cap precedes ranking, and what fusion "
            "depth is used by hybrid search?"
        ),
    ),
    (9, 22, "Which PostgreSQL schema revision is required and what active-job quotas apply?"),
    (10, 18, "What bounds a semantic indexing call's chunk count and provider concurrency?"),
    (11, 15, "Are remote models allowed, and does local inference have a measured compute cost?"),
    (
        12,
        16,
        (
            "Where is the packaged frontend served, and what deadline protects"
            " a local-provider HTTP call?"
        ),
    ),
    (
        13,
        17,
        "What numeric identity runs the application image, and how large may provider output be?",
    ),
    (
        14,
        20,
        "Does the worker have a health probe, and what is the default lease duration?",
    ),
    (
        15,
        23,
        "Which inference cost remains unknown, and what is the minimum official dataset size?",
    ),
    (16, 21, "What is the provider HTTP deadline, and how many ingestion attempts are permitted?"),
    (17, 24, "What provider-output size cap and hybrid rank-fusion formula are documented?"),
    (18, 22, "What provider concurrency and global active-ingestion limits bound work?"),
    (
        19,
        23,
        (
            "What source-containment check constrains claims, and how many "
            "cases are needed for official evaluation?"
        ),
    ),
]

UNANSWERABLE = [
    "What is Atlas's deployed public production hostname?",
    "Which AWS region hosts the production Atlas database?",
    "What is the monthly electricity bill attributable to Atlas inference?",
    "Who personally reviewed every case in the completed 100-case benchmark?",
    "What is Atlas's official human-reviewed hybrid Recall@5 score?",
    "Which reranker won the completed held-out quality comparison?",
    "What is the measured p99 latency with 500 simultaneous users?",
    "What uptime percentage did production Atlas achieve during September 2026?",
    "Which support email address should customers use for production incidents?",
    "What is the production identity provider's issuer URL?",
    "Which S3 bucket stores the verified production backups?",
    "What recovery time was achieved in the last successful production backup restore?",
    "What numeric energy consumption was measured for one qwen3 answer?",
    "What peak GPU temperature was measured during the final 100-case benchmark?",
    "Which exact external penetration-testing report certified Atlas?",
    "What was the final held-out semantic faithfulness score assigned by human reviewers?",
    "Which measured cosine threshold was selected to optimize unanswerable questions?",
    "What is the tenant count in Atlas's live production deployment?",
    "Which production TLS certificate fingerprint is currently deployed?",
    "What exact per-query compute cost was measured on the target production hardware?",
]

# Date/scope reconciliation, including explicitly flagged weak conflict proxies.
TEMPORAL = [
    (
        (
            "Does the initial note that Docker was unavailable still describe "
            "the later packaging evidence?"
        ),
        "plan",
        "Docker engine was unavailable",
        "deployment",
        "Passed initial application image build",
    ),
    (
        "Did the initial empty Ollama model inventory remain empty in the provider verification?",
        "plan",
        "model list was empty",
        "provider",
        "actual local embeddings, generation and empty-evidence abstention passed",
    ),
    (
        (
            "Should the initial repository inventory be used to conclude that "
            "no frontend currently exists?"
        ),
        "plan",
        "No code, manifests, tests, or nested instructions exist",
        "readme",
        "a React document workspace",
    ),
    (
        (
            "Does the original frontend milestone's no-generation statement "
            "include the later answer UI increment?"
        ),
        "frontend",
        (
            "No generation, vector search, benchmark results or public "
            "deployment are claimed by this milestone"
        ),
        "frontend",
        "This increment supersedes M3's statement that generation UI was absent",
    ),
    (
        (
            "Is vector integration still entirely absent because the provider "
            "evidence listed it as remaining work?"
        ),
        "provider",
        "complete vector/hybrid integration",
        "vector",
        "integrates explicit semantic indexing, exact cosine search and reciprocal rank fusion",
    ),
    (
        (
            "Does the evaluation foundation's blocked-vector status override "
            "the later vector API verification?"
        ),
        "foundation",
        "Blocked: real human-checked benchmark, vector/hybrid/reranking",
        "vector",
        "Authenticated index, vector/hybrid search and answers",
    ),
    (
        (
            "Does the old evaluation-foundation record mean that the "
            "answer-observation runner is still absent?"
        ),
        "foundation",
        "generated answer quality and production performance",
        "readme",
        (
            "The runner can optionally measure actual generated-answer "
            "citations, abstention and token usage"
        ),
    ),
    (
        (
            "Does the frontend delegate's pending browser work mean no real "
            "viewport checks were subsequently performed?"
        ),
        "frontend",
        (
            "Parent task owns browser/live-server, narrow viewport, keyboard "
            "and visual contrast checks"
        ),
        "browser",
        "Widths 375, 768, 1440: no horizontal overflow",
    ),
    (
        (
            "How should the provider document's remaining deployment "
            "verification be interpreted alongside the packaging record?"
        ),
        "provider",
        "deployment verification",
        "deployment",
        "This is local Docker Desktop verification, not a public deployment",
    ),
    (
        (
            "Are the original 15 frontend tests the same as the latest "
            "documented component-test count?"
        ),
        "frontend",
        "15 tests across two files",
        "readme",
        "passed 25 component tests",
    ),
    (
        "Does the M1 test count of 30 represent the latest complete backend suite?",
        "state",
        "passed 30 tests, 96% statement coverage",
        "readme",
        "132 tests with 93% statement coverage",
    ),
    (
        "Does the initial SQLite baseline establish that PostgreSQL was never implemented?",
        "plan",
        "SQLite is a development backend, not proof of PostgreSQL compatibility",
        "pg",
        "Real PostgreSQL/worker suite, final run",
    ),
    (
        (
            "Does a native model-enabled browser journey imply that the "
            "packaged container profile enables models?"
        ),
        "browser",
        "Passed against real loopback API and Ollama",
        "deployment",
        "Models are disabled in this container profile",
    ),
    (
        (
            "Does a successful synthetic provider smoke establish completion "
            "of the human benchmark requirement?"
        ),
        "provider",
        "the synthetic smoke was used during development and is not a holdout or benchmark",
        "vector",
        "The 100-case human-reviewed benchmark remains incomplete",
    ),
    (
        (
            "Does a dependency audit with zero findings contradict the "
            "documentation's remaining security limits?"
        ),
        "frontend",
        "zero reported vulnerabilities",
        "deployment",
        "they do not guarantee absence of vulnerabilities",
    ),
]


def build_drafts(root: Path) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    snapshots = {path: (root / path).read_bytes() for path in SOURCES.values()}

    def reference(alias: str, anchor: str) -> dict[str, Any]:
        path = SOURCES[alias]
        raw = snapshots[path]
        source = raw.decode("utf-8")
        pattern = r"\s+".join(re.escape(word) for word in anchor.split())
        matches = list(re.finditer(pattern, source))
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one evidence anchor in {path}: {anchor}")
        match = matches[0]
        return {
            "path": path,
            "content_sha256": hashlib.sha256(raw).hexdigest(),
            "start": match.start(),
            "end": match.end(),
            "quote": match.group(),
        }

    cases: list[dict[str, Any]] = []

    def add(category: str, question: str, refs: list[dict[str, Any]], critique: str) -> None:
        cases.append(
            {
                "case_id": f"atlas-docs-{len(cases) + 1:03d}",
                "category": category,
                "question": question,
                "answerable": category != "unanswerable",
                "expected_facts": [re.sub(r"\s+", " ", ref["quote"]) for ref in refs],
                "source_references": refs,
                "human_reviewer": None,
                "reviewed_at": None,
                "synthetic": True,
                "ai_review": {
                    "reviewer": "Codex",
                    "kind": "AI",
                    "date": "2026-10-24",
                    "status": "development_only",
                    "critique": critique,
                },
                "scoring_notes": (
                    "AI-authored development draft. Assess semantic sufficiency, not "
                    "just keyword overlap. "
                )
                + (
                    "Do not invent a value; acknowledge that the corpus does not establish it."
                    if not refs
                    else (
                        "All referenced facts are required; accept semantically equivalent wording."
                    )
                ),
            }
        )

    for alias, anchor, question in FACTS:
        add(
            "direct",
            question,
            [reference(alias, anchor)],
            (
                "Source supports the factual target. Short anchor and lexical "
                "wording make this easier than real support traffic."
            ),
        )
    for first, second, question in PAIRS:
        a, b = FACTS[first], FACTS[second]
        if a[0] == b[0]:
            raise ValueError("Multi-document draft must use distinct files")
        add(
            "multi_document",
            question,
            [reference(a[0], a[1]), reference(b[0], b[1])],
            (
                "Both files are needed, but the conjunction is artificial and does"
                " not establish difficult multi-hop reasoning."
            ),
        )
    for question in UNANSWERABLE:
        add(
            "unanswerable",
            question,
            [],
            (
                "The frozen project corpus does not establish the requested "
                "measurement or deployment detail. Negative cases are concentrated"
                " on known missing project capabilities."
            ),
        )
    for index, (question, a, x, b, y) in enumerate(TEMPORAL):
        add(
            "conflicting_outdated",
            question,
            [reference(a, x), reference(b, y)],
            (
                "Reconcile dates and scope; do not treat historical milestone "
                "limits as current absence. "
            )
            + (
                (
                    "Weak conflict proxy: this is a scope distinction rather than "
                    "contradictory source facts. Replace before a representative "
                    "conflict benchmark."
                )
                if index >= 12
                else (
                    "Temporal evidence is valid, but questions name the expected "
                    "historical interpretation."
                )
            ),
        )
    for index, question in enumerate(PARAPHRASES):
        alias, anchor, _ = FACTS[index]
        add(
            "difficult",
            question,
            [reference(alias, anchor)],
            (
                "Paraphrases an existing direct fact. Difficulty is unmeasured; "
                "related cases must stay in the same split to prevent leakage."
            ),
        )
    expected = {
        "direct": 25,
        "multi_document": 20,
        "unanswerable": 20,
        "conflicting_outdated": 15,
        "difficult": 20,
    }
    if Counter(case["category"] for case in cases) != expected:
        raise ValueError("Draft distribution is incomplete")
    if len({case["question"] for case in cases}) != 100:
        raise ValueError("Duplicate question text")
    return cases, snapshots


def write_drafts(root: Path, output: Path) -> None:
    cases, snapshots = build_drafts(root)
    # Validate every anchor before creating output; never overwrite a frozen set.
    output.mkdir(parents=True, exist_ok=False)
    for path, raw in snapshots.items():
        target = output / "sources" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    payload = "\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n"
    (output / "drafts.jsonl").write_bytes(payload.encode("utf-8"))
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "status": "AI-authored and AI-critiqued development drafts; not human reviewed",
                "official": False,
                "case_count": len(cases),
                "category_counts": dict(Counter(case["category"] for case in cases)),
                "drafts_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                "sources": {
                    path: hashlib.sha256(raw).hexdigest() for path, raw in snapshots.items()
                },
                "binding": (
                    "Source spans are real; indexed passage IDs must be bound after ingestion."
                ),
                "limitations": [
                    "Same agent authored and reviewed cases",
                    "Project-specific corpus",
                    "Repeated facts across categories; no holdout",
                    "Three weak conflict proxies",
                    "No retrieval or answer score has been measured by this preparation command",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"drafts": len(cases), "human_reviewed": 0, "output": str(output)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    write_drafts(args.source_root, args.output)


if __name__ == "__main__":
    main()
