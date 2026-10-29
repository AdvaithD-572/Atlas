# Atlas local UI

Run the API on `127.0.0.1:8000` using the repository setup instructions. Then:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173 and enter a locally provisioned Atlas access token.
The token lives only in page memory. Disconnect or reload to clear it. No external
API, analytics, remote font, storage service, or paid service is used.

Document keys are stable identities within your account. Reusing a key with new
text replaces the indexed version; unchanged content keeps its version. The UI
accepts UTF-8 `.txt`, `.md`, and `.markdown` files or pasted text. The default
response mode displays retrieved excerpts and exact character spans. When the
authenticated capabilities endpoint enables generation, a second mode asks the
local model to select verbatim claims with validated citations. Conflicting
evidence and insufficient evidence have explicit states. This is extractive
grounding, not unrestricted synthesis or a correctness guarantee. The server
remains responsible for authorization, size quotas, parsing and persistence.

```powershell
npm test
npm run typecheck
npm run build
npm run test:contract
npm audit
```

`test:contract` starts an isolated in-process FastAPI app using the root `.venv`
Python, temporary migrated storage, and explicit synthetic test content. It sends
real API requests and validates the serialized responses using the UI parsers.
Set `ATLAS_PYTHON` if the project's Python environment is elsewhere. It does not
use existing user documents or credentials. Answer contract checks use an
explicit mock Ollama HTTP transport while exercising actual API orchestration,
provider validation and serialization. They do not verify local-model inference.
Component tests mock HTTP responses; neither test layer is a substitute for
browser end-to-end verification.

Dependencies are exact-pinned in `package.json` and `package-lock.json`. Vite is a
loopback-only development server. `npm run build` creates `dist/`; deployment
requires a static host and same-origin `/v1` routing to the API, HTTPS for remote
access, and security headers. This milestone does not configure a public host.
The API's restrictive CSP applies to JSON endpoints and must not be reused
unchanged for UI HTML. Do not expose the development server as a public service.

The runtime response schemas in `src/api.ts` consume the authoritative Pydantic
contract in `atlas/schemas.py` and `atlas/retrieval.py`. Update both sides and run
`test:contract` when that boundary changes. The validator accepts both the SQLite
`fts5-overlap-v1` and planned PostgreSQL `postgres-simple-overlap-v1` retrieval
versions; accepting a version is not evidence its backend is verified. Answer
responses must use the server's `verbatim_claims_and_citations` contract, with
claims and quotes resolving to supplied passages. Ordinary requests time out
after 20 seconds; model answers allow 130 seconds. The server can continue work
after a browser disconnect, so don't repeatedly retry a slow model request.
No benchmark or model-quality result is fabricated.
