# AGENTS.md --- Atlas

## Grounded Knowledge Intelligence Platform

This file is the durable engineering constitution for this repository.
Apply it to all work in this repository unless a higher-priority
platform instruction or an explicit user decision overrides it.

## 1. Mission and success criteria

Build **Atlas**, a production-style retrieval-augmented generation (RAG)
platform for technical documentation. Users ingest authorized documents,
ask questions, inspect source-backed answers, and evaluate retrieval and
answer quality using a reproducible benchmark.

The project is intended to demonstrate applied AI engineering: reliable
ingestion, retrieval experiments, grounded generation, evaluation,
security, observability, deployment, and maintainable software
engineering. It is not merely a chat UI around an LLM API.

### Required outcomes

1.  A working document lifecycle: ingest, parse, chunk, index, version,
    re-index, inspect status, and delete.
2.  A working query path that retrieves evidence, generates a grounded
    answer, and links citations to real source locations.
3.  A retrieval evaluation harness comparing lexical, vector, and hybrid
    retrieval; evaluate reranking separately.
4.  A human-checked evaluation dataset with at least 100 cases across
    answerable, multi-document, unanswerable, conflicting/outdated, and
    difficult/paraphrased questions.
5.  Separate metrics for retrieval, answer correctness, citation
    quality, faithfulness, abstention, latency, failures, and estimated
    cost.
6.  Authentication and authorization that prevent unauthorized document
    access, including in retrieval, cached results, citations,
    background jobs, and deletion.
7.  Security and failure handling for malformed documents, provider
    errors, prompt injection, conflicting evidence, and insufficient
    evidence.
8.  A deployable API and usable frontend, automated tests, CI,
    structured observability, documentation, and reproducible evaluation
    commands.
9.  Evidence-based documentation. Never invent benchmark results, test
    outcomes, scale claims, or deployment status.

A portfolio project cannot guarantee employment. Optimize for
demonstrable engineering competence and honest, reproducible evidence.

## 2. Source of truth, scope, and assumptions

At repository start, inspect the actual working tree and available
user-provided materials. Do not claim to have inspected code that does
not exist. If the repository is empty, treat this file as the initial
product and architecture brief.

Create and maintain concise project artifacts when useful: -
`README.md`: user-facing setup, features, demo, limitations, and
verified results. - `docs/PRD.md`: functional and non-functional
requirements and explicit non-goals. - `docs/architecture.md`:
components, boundaries, data flows, and design decisions. -
`docs/evaluation.md`: dataset protocol, metrics, experiment matrix, and
result interpretation. - `docs/security.md`: threat model,
access-control model, and security test cases. - `docs/operations.md`:
local setup, configuration, migrations, deployment, health checks, and
troubleshooting. - `BUILD_STATE.md`: only for substantial multi-session
work; record status and evidence, not speculative completion.

Create documents when their content is ready to be authoritative; do not
create empty placeholders just to satisfy this list. Do not duplicate
this file verbatim in other documents.

### Decision classification

When recording a decision, label it as: - **Confirmed**: explicitly
specified in this file or approved by the user. - **Discovered**:
verified from repository files, executed behavior, or authoritative
documentation. - **Proposed default**: a reversible choice selected to
unblock implementation. - **Unknown/blocker**: cannot be resolved safely
without user input or access.

The intended stack is a proposed default, not evidence of an existing
implementation: - Python, FastAPI, Pydantic. - PostgreSQL with pgvector
and PostgreSQL full-text search. - React with TypeScript for the UI. - A
background worker and queue for ingestion; Celery/Redis is the default
if the added operational complexity is justified. - Docker Compose for
local reproducibility. - pytest for Python tests; use the package
manager and test tools actually established by the repository for the
frontend. - A pluggable embedding/generation provider interface, with
one provider implemented and verified end to end before adding another.

Use the simplest architecture that meets requirements. Start as a
modular application plus worker, not a microservice fleet. Reconsider a
technology choice only with evidence, compatibility constraints, or a
clear product need. Record meaningful trade-offs in
`docs/architecture.md`.

## 3. Instruction precedence and repository discovery

Follow this order: 1. Platform and safety requirements. 2. Explicit
user-approved requirements and constraints. 3. Applicable `AGENTS.md`
files, including more-specific instructions in the current directory. 4.
Verified project documentation and established code conventions. 5. This
file's proposed defaults. 6. General engineering judgment.

Codex recognizes `AGENTS.md` as repository guidance. Before substantial
work, inspect the repository root and current working directory, read
this file and any applicable nested `AGENTS.md`, then inspect only the
relevant source, tests, configs, and docs. More-specific nested
instructions apply to their subtree; resolve genuine conflicts
explicitly instead of silently choosing an interpretation. Do not reread
every document for trivial changes when it is not relevant.

Inspect before modifying. Preserve unrelated user changes. Never run
destructive Git operations, overwrite user work, reset branches, or
discard changes without explicit authorization.

## 4. Product behavior and functional requirements

### 4.1 Document ingestion and lifecycle

-   Accept PDF, Markdown, HTML, and plain text only when parsers are
    implemented and tests cover them.
-   Validate content type, size, encoding, and parser outcome. Treat
    uploaded files as untrusted input; avoid unsafe archive extraction
    or arbitrary file paths.
-   Preserve source identity and useful locations, such as page number,
    heading, URL, and character span where available.
-   Chunking strategy, chunk size, overlap, normalization, and embedding
    model must be configurable and recorded with index metadata.
-   Track a stable document ID, version/content hash, parser version,
    chunking configuration, embedding model/version, ingestion status,
    timestamps, and ownership scope as appropriate.
-   Re-uploading unchanged content should not create duplicate chunks.
    Changed content must trigger controlled re-indexing.
-   Background jobs must expose meaningful status, bounded retries,
    timeout behavior, and actionable errors. Avoid retrying permanent
    validation errors indefinitely.
-   Deletion must remove or invalidate all derived chunks, embeddings,
    caches, citations and job artifacts covered by the retention policy.
    Verify tenant/user ownership before every deletion.
-   Partial ingestion failure must not leave the document appearing
    fully indexed. Use transactions or explicit state transitions and
    cleanup/reconciliation.

### 4.2 Retrieval and generation

-   Implement separate lexical-search and vector-search baselines before
    hybrid retrieval.
-   Implement hybrid fusion (for example reciprocal rank fusion) only
    with tests and an explanation of its configuration.
-   Evaluate a reranker as a separate stage; keep it only if measured
    benefit justifies cost and latency.
-   Retrieval must enforce authorization before returning passages.
    Never rely on frontend filtering to enforce access.
-   The generator must use retrieved evidence, avoid presenting
    unsupported claims as facts, and return citations that resolve to
    actual indexed source passages.
-   Represent evidence and citations as structured data; do not parse
    arbitrary model prose to infer trusted citation IDs.
-   Support an explicit insufficient-evidence/abstention outcome. Do not
    force an answer when retrieval is empty or evidence is inadequate.
-   Handle conflicting or stale sources transparently; preserve source
    dates/versions when known and avoid silently inventing a resolution.
-   Keep prompts, model IDs, retrieval settings, chunking settings, and
    relevant configuration versioned or recorded per run.
-   Make provider/model configuration swappable through a small
    interface. Do not add provider-specific branching throughout the
    application.
-   Apply timeouts, bounded retries, rate-limit handling,
    response-schema validation, and user-safe error messages to external
    calls.

### 4.3 Evaluation

-   Create at least 100 human-checked cases before claiming the
    benchmark requirement is complete. Each case should record
    answerability, expected facts or acceptable answer, relevant source
    passages, category, and scoring notes.
-   Include direct factual retrieval, multi-document questions,
    unanswerable questions, conflicting/outdated evidence, and
    paraphrase/difficult-retrieval cases. The planned starting
    distribution is 25/20/20/15/20 respectively; change it only with a
    documented reason.
-   Separate retrieval metrics (such as Recall@k and MRR) from answer
    metrics (correctness, faithfulness/grounding, citation correctness,
    and abstention quality).
-   Document metric definitions, denominator, evaluator version, known
    limitations, and whether a metric is deterministic, human-rated, or
    model-judged.
-   Use model-based judges only as supporting evidence; validate them
    against human review and do not treat their scores as ground truth.
-   Compare lexical, vector, hybrid, and optional reranking
    configurations on the same frozen dataset. Record config/model
    versions, latency, failures, and estimated cost.
-   Establish baselines before tuning. Do not tune against the final
    test set without disclosure; reserve a holdout subset where
    practical.
-   Do not invent target scores. Set acceptance thresholds before final
    evaluation when possible, justify them, and report actual results
    including regressions.
-   Save machine-readable results (for example JSON/CSV) and a
    human-readable report. Make the evaluation command reproducible from
    a clean checkout.

### 4.4 UI and user experience

-   Build a coherent, responsive interface for document management,
    ingestion status, question/answer interaction, source inspection,
    and evaluation results.
-   Provide loading, empty, success, error, and retry states. Never
    display fabricated documents, metrics, or answer content as if it
    came from the backend.
-   Citation interactions must open the correct source and location.
    Clearly distinguish retrieved excerpts from generated answer text.
-   Show abstention and conflicting-evidence states clearly.
-   Make interactive controls keyboard-accessible, use semantic HTML and
    visible focus, label form fields, and handle validation errors
    accessibly.
-   Use realistic seeded data only in explicit development/demo mode;
    production paths must use real API responses.
-   Test representative desktop and narrow viewport layouts. Do not
    spend time on decorative polish before core workflows, security, and
    evaluation work.

## 5. Architecture and implementation rules

### 5.1 Boundaries

Keep these responsibilities distinct: - API/routes: HTTP contracts,
authentication dependency wiring, request/response serialization. -
Application/services: use cases and orchestration. - Domain/schemas:
stable types, validation, state and business rules. - Ingestion:
parsing, normalization, chunking, embedding, indexing and cleanup. -
Retrieval: query processing, authorization filtering,
lexical/vector/hybrid search and reranking. - Generation: prompt
construction, provider calls, structured output validation, citations
and abstention. - Evaluation: dataset loading, metric computation,
experiment execution and report generation. - Persistence: database
models, repositories, transactions and migrations. -
Security/observability: shared policies and instrumentation.

Discover actual paths before relying on these conceptual boundaries.
Avoid circular imports and avoid letting route handlers become the
business-logic layer. Do not create abstractions with only one trivial
caller unless they isolate a real boundary or make tests substantially
better.

### 5.2 Python and TypeScript quality

-   Use type hints for public Python interfaces and strict TypeScript
    settings where the frontend toolchain supports them.
-   Validate untrusted inputs at system boundaries with Pydantic or
    established project equivalents.
-   Use structured error types and consistent API error responses; do
    not swallow exceptions or return success-shaped fallback data on
    failure.
-   Keep secrets and environment-specific values out of source code.
    Validate required configuration at startup and provide a safe
    `.env.example` with placeholders only.
-   Use async operations only where they improve I/O behavior; do not
    block the event loop with synchronous heavy work.
-   Use bounded concurrency and close database, HTTP and provider
    clients correctly.
-   Keep database transactions short and explicit. Use migrations for
    schema changes; do not rely on ad hoc production schema mutation.
-   Avoid global mutable state for user-specific or request-specific
    data.
-   Avoid logging full documents, prompts, access tokens, secrets, or
    sensitive user content by default. Prefer IDs, counts, hashes,
    timings and redacted diagnostics.
-   Follow the existing formatter, linter, type checker and package
    manager after discovering them. Do not invent commands or add
    overlapping tools without reason.

### 5.3 Data contracts and API

-   Use explicit request/response schemas, stable IDs, pagination where
    lists may grow, and consistent validation/error semantics.
-   Document public endpoints and their authorization requirements.
-   Enforce ownership on reads, writes, citations, background jobs and
    cached results.
-   Use idempotency or deduplication for operations that may be retried.
-   Avoid leaking internal exception details to clients.
-   Treat API/schema changes as compatibility changes; update clients
    and tests together.

## 6. Security and privacy

Threats to address include malicious uploads, parser vulnerabilities,
prompt injection in retrieved content, cross-user data leakage,
unauthorized citations, provider compromise/errors, secret leakage,
denial of service, and accidental retention of deleted data.

Mandatory controls: - Authenticate users for non-public data and
authorize every resource access server-side. - Use a consistent
ownership/tenant model. If multi-tenancy is implemented, every query,
retrieval result, cache key, background task and deletion path must
preserve isolation. - Apply upload size/type limits, safe temporary
paths, parser timeouts/resource limits where feasible, and never execute
uploaded content. - Treat retrieved text as untrusted evidence, not
instructions. Prompts alone are not a security boundary; retrieval
authorization and tool/data permissions must be enforced in code. - Test
prompt-injection attempts, including documents instructing the model to
reveal secrets or other users' content. - Keep API keys in
environment/secret management; never commit them, echo them in logs, or
expose them to the browser. - Use parameterized SQL/ORM operations and
safe output rendering. Do not use unsafe deserialization. - Set request
and provider timeouts, payload limits, rate limits where appropriate,
and bounded retries to reduce abuse and cost. - Minimize sensitive data
in logs and evaluation artifacts. Define retention/deletion behavior in
documentation. - Add regression tests for every discovered security
defect. - Never disable authorization, TLS validation, input checks, or
security tests to make the demo pass.

## 7. Reliability, performance, and operations

-   Bound ingestion concurrency, provider concurrency, retries, queue
    growth, document sizes and query work.
-   Distinguish transient failures from permanent failures. Use
    exponential backoff with jitter only where appropriate and respect
    provider retry guidance.
-   Prevent duplicate processing and stale writes using idempotency
    keys, content hashes, job state checks or database constraints as
    appropriate.
-   Add health/readiness checks that reflect actual dependencies; do not
    report ready if required storage is unavailable.
-   Record request/job IDs, stage timings, retrieval counts,
    provider/model identifiers, token usage when available, estimated
    cost, errors and retries. Redact sensitive values.
-   Track latency distributions and failures under a documented
    workload. Do not claim performance at scale without representative
    measurements.
-   Cache only when correctness and authorization are preserved. Include
    model/config/version and access scope in cache keys; invalidate on
    document updates/deletion.
-   Document database migration and rollback considerations. Never run
    destructive production migrations or delete production data without
    explicit authorization.
-   Make local setup reproducible with Docker Compose if supported by
    the final stack.

## 8. Dependencies and external integrations

-   Inspect existing manifests and lockfiles before adding or upgrading
    dependencies.
-   Prefer maintained, appropriately licensed packages with a clear
    purpose. Check compatibility and known security concerns where
    practical.
-   Pin or constrain dependencies using the established package manager
    and keep lockfiles consistent.
-   Do not introduce a paid service, account requirement, or additional
    provider without explaining the need and offering a low-cost/local
    alternative where feasible.
-   Mock external providers for isolated unit tests, but label mocks
    clearly. A mock is not proof that the real provider integration
    works.
-   Validate provider responses and test missing credentials, timeouts,
    rate limits, malformed responses and service unavailability.
-   Never invent credentials or claim a cloud deployment succeeded
    without observed evidence.

## 9. Testing and verification

Discover the actual commands from manifests, CI workflows, and existing
docs. Do not assume a command exists. If a check cannot run because a
service, credential, package, GPU or network access is unavailable,
report it as blocked/skipped with the reason and run the strongest safe
alternative.

Risk-based test layers: 1. Unit: parsing/chunking, document hashes,
ranking/fusion, citation mapping, abstention logic, metrics, validation
and policy decisions. 2. Integration: database/vector search,
migrations, ingestion lifecycle, worker retry/recovery, provider adapter
contract and authorization. 3. API/UI: upload/query/delete flows,
citation navigation, loading/error states and access-denied behavior. 4.
Security: cross-user retrieval, prompt injection, malicious/malformed
files, path handling, secret leakage and deletion consistency. 5.
Evaluation: frozen dataset, metric unit tests, experiment
reproducibility and report generation. 6. Operational: clean startup,
health checks, migration behavior, CI and deployment smoke tests.

For every task: - Establish the relevant baseline and inspect existing
failures. - Add/update tests for changed behavior and regression bugs. -
Run the narrowest relevant tests, then adjacent integration tests. - Run
broader checks before a milestone or completion claim. - Investigate
failures; do not suppress, skip, or weaken tests without explicit
documented justification. - Distinguish implementation status from
verification status. - Report exact checks run and their outcomes.

A passing suite does not prove answer quality, data isolation, or
production suitability; use the separate benchmark and security tests as
well.

## 10. Tool, skill, and subagent use

At the start of substantial work, inspect available tools, skills, MCP
integrations, and subagents in the current Codex environment. Read the
instructions for a relevant skill before applying it. Use specialized
capabilities only when they materially improve this task; do not invoke
everything indiscriminately.

Good candidates when actually available include: - repository
exploration and code review, - test-driven development, -
security/threat-model review, - frontend accessibility or browser
verification, - database/migration review, - evaluation/benchmark
analysis, - documentation review.

Delegate independent reviews only when the task can be split cleanly.
Give each delegate a bounded question and expected evidence. Avoid
concurrent edits to the same files. Independently verify important
findings and integrate them into the repository. If a skill or tool is
unavailable, continue with ordinary methods and disclose meaningful
limitations.

For OpenAI/Codex-specific APIs or behavior, prefer current official
OpenAI developer documentation or a configured official documentation
MCP if available. For other dependencies, prefer their official docs and
inspect the versions actually installed/locked.

## 11. Autonomous workflow, planning, and recovery

For substantial features, work in small end-to-end increments: 1.
Inspect the relevant code, instructions, tests and current Git state. 2.
Map the requirement to components, dependencies and acceptance criteria.
3. Create/update a short implementation plan when the work spans
multiple subsystems. 4. Implement one vertical slice at a time. 5. Test
immediately and fix failures before broadening scope. 6. Integrate the
UI, API, persistence, observability and tests rather than leaving
disconnected modules. 7. Update relevant documentation and progress
state with evidence. 8. Perform a final requirements-to-tests audit.

Make reversible implementation decisions independently. Ask the user
only when blocked by a materially ambiguous product/security choice,
unavailable credentials/permissions, irreversible/destructive action,
meaningful financial risk, or a decision that cannot be safely inferred.

For multi-session work, use `BUILD_STATE.md` only if it materially
improves continuity. Track each requirement as `NOT_STARTED`,
`IN_PROGRESS`, `IMPLEMENTED`, `VERIFIED`, or `BLOCKED`. `VERIFIED` means
the code exists, acceptance criteria were checked, relevant checks were
executed, and evidence is recorded. On resumption, inspect the
repository and validate the recorded state rather than trusting it
blindly.

Do not stop after producing a plan, scaffold, mock UI, or disconnected
code. Continue through integration and verification unless the user
explicitly asks for planning only or a genuine blocker requires a
handoff.

## 12. Definition of done

A task is complete only when: - The intended behavior is integrated into
the real application. - Acceptance criteria and relevant edge cases are
addressed. - Relevant tests and checks have actually run, with failures
explained. - Authorization, privacy, error handling and operational
implications are considered. - Documentation/configuration are updated
where needed. - No known critical regression introduced by the change
remains unresolved. - Remaining limitations and unavailable checks are
explicit.

Atlas is portfolio-ready only when: - The full ingest → retrieve →
grounded answer → citation path works in the running application. -
Document versioning, deduplication, deletion, and authorization have
verified tests. - The benchmark has at least 100 human-checked cases and
a reproducible report. - Lexical, vector, hybrid, and any claimed
reranking comparison uses the same evaluation set. - Results include
actual metrics, latency/cost measurements where available, and
limitations. - The UI handles empty/loading/error/abstention states and
works at representative viewport sizes. - CI, Docker/local setup,
security checks, and documentation have been verified. - The README
clearly separates implemented features from planned work and never
overstates scale, reliability, or results.

Final reports must distinguish **passed**, **failed**, **skipped**, and
**blocked** checks. Never say "production-ready" merely because the app
starts or the happy path works.


## Mandatory Skill Discovery and Usage

Before beginning implementation, scan all accessible skill libraries and discover relevant installed, project-local, and environment-provided skills. Read the instructions for every skill applicable to the planned work and maintain a skill-to-task mapping.

**Every task and milestone MUST use all relevant available skills.** Before starting implementation, testing, debugging, reviewing, refactoring, security assessment, integration, deployment, or documentation, consult the mapping, identify applicable skills, read their instructions, and invoke or follow them using the supported mechanism.

Skill usage is continuous and mandatory. Do not merely list skills, claim usage without evidence, silently skip relevant skills, or force irrelevant skills into unrelated work. Re-scan the available library when new work requires additional capabilities. If a skill is missing or inaccessible, document the limitation and use the best available alternative. If automatic invocation is unavailable, follow the skill instructions manually.

Maintain `docs/engineering/skill-usage.md` with discovered skill locations, task mappings, actual usage records, limitations, and verification evidence. Keep the mapping updated throughout development. Do not fabricate skill availability, execution, or results.

Skill instructions supplement but never override higher-priority instructions, project acceptance criteria, or security requirements. If a conflict exists, follow the higher-priority requirement and document the conflict.
