# Security model and current limits

The local application trusts the operator and OS account, not uploads or clients.
It is a loopback development service. Bearer credentials are generated randomly;
only SHA-256 digests are used by the API, compared in constant time. Tokens grant
access only to their configured owner scope. UUIDs are not an authorization control.

| Threat | Current control / verification |
|---|---|
| Cross-owner read/delete/citation | Owner predicates on every resource query; two-owner API tests |
| Partial replacement or concurrent duplicate | Serialized transaction, unique owner/key, rollback and concurrent-upload tests |
| Malformed/large upload | UTF-8 strict decode, nonempty/control validation, MIME allowlist, streaming byte limit, timeout |
| Chunk amplification | Overlap <= half size, arithmetic preflight chunk-count cap, regression test |
| SQL injection / unsafe paths | Bound SQL parameters; upload keys never used as filesystem paths |
| Deleted/stale source access | Cascades, new chunk UUIDs on reindex, stale-citation/deletion tests |
| Secret/content logging | Safe error envelope, Pydantic input hiding, structured allowlisted logs and tests |
| Concurrent credential provisioning | Exclusive lock, exclusive token create, atomic registry replacement, rollback tests |
| Resource pressure | Byte/chunk/owner quotas, process-local request rate limit; launch concurrency bound |

## Provider, worker and frontend controls

The local generation model has no tools or shell execution facility. Retrieval
authorizes evidence before inference; claims must reproduce nonempty source text,
and structured citation IDs must resolve to current owner passages after inference.
Model text is never interpreted as an authorization decision. These controls
bound data access and provenance; they do not prove that an extracted sentence is
relevant, true, up to date or a correct resolution of conflicting documents.

Ollama calls accept only loopback local models, validate response identity/schema,
bound response bytes, concurrency, retries and elapsed time, and reject malformed
vectors and fabricated/cross-source citations. Adversarial provider and question
tests cover those conditions. Model digests scope embeddings; SQL materializes
authorized candidates before cosine distance. Publication rechecks the source
snapshot to prevent stale embedding writes.

Durable jobs retain owner/configuration and require a valid lease plus a configured
owner before publication. Deletion and newer writes invalidate stale work.
Terminal raw payloads are cleared. See the PostgreSQL evidence for retention
limits and the corrected local credential exposure during testing.

The browser renders source/answer text through React text nodes, validates API
responses, stores tokens only in memory, and aborts stale requests on disconnect.
The packaged frontend uses a self-only CSP and no cookies. Cookie sessions would
require a separate CSRF design. Container runtime is non-root, read-only and
loopback-published; the operator still controls Docker and local credentials.

The local Compose API/worker now use a restricted database login; the bootstrap
administrator is reserved for migrations. Tests deny DDL, TRUNCATE, migration
metadata writes and role administration. The runtime still uses application owner
predicates; it is not a separate database role per tenant. Worker readiness requires
actual loop progress and a reachable compatible schema. Private files keep mode
0600 on Linux, with explicit matching non-root container UID; a mismatched UID is
verified unable to read them. No world-readable secret workaround is used.

Optional local TLS verifies an explicitly trusted certificate and rejects unknown
trust and wrong hostnames. A real disposable backup/restore verifies row integrity,
owner isolation, vectors, jobs and citations. These controls are reproducible in
the shared package checks; they do not supply a public certificate lifecycle or
an off-host encrypted backup retention service.

PDF parsing now uses an isolated child, one-process concurrency, a wall timeout,
bounded pages/output/decoded streams, and Linux CPU/address-space limits. HTML is
extracted as inert text without remote fetching; React escapes displayed excerpts.
Windows does not enforce an OS memory ceiling on the parser. Synthetic security
tests include encrypted, malformed, empty, excessive-page, deep HTML and timeout
cases; parser containment is not a claim that arbitrary hostile PDFs are harmless.

Pending: public identity/certificate operations,
distributed limits, operator-selected backup retention, human semantic
prompt-injection review and comprehensive penetration testing. No Strix scanner
is installed; adversarial tests and manual review are not a complete penetration
test. See operations.md for credential and deletion/backup handling.

