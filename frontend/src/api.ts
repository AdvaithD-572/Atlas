import { z } from 'zod';

// The provider's atlas/schemas.py and atlas/retrieval.py own this contract.
// Validate the values used by the UI; additive provider fields are allowed.
const count = z.number().int().nonnegative();
export const documentSchema = z.object({
  id: z.string().uuid(), source_key: z.string(), version: count.positive(),
  status: z.literal('indexed'), chunk_count: count,
  media_type: z.enum(['text/plain', 'text/markdown', 'text/html', 'application/pdf']),
  content_hash: z.string(), parser_version: z.string(),
  chunk_size: count.positive(), chunk_overlap: count,
  normalization: z.enum(['none-v1', 'pdf-text-v1', 'html-text-v1']), embedding_model: z.null(),
  created_at: z.string(), updated_at: z.string(),
});
export const passageSchema = z.object({
  id: z.string().uuid(), document_id: z.string().uuid(), source_key: z.string(),
  version: count.positive(), ordinal: count, start: count, end: count, text: z.string(),
  page_number: count.positive().max(200).nullable().optional(),
  heading: z.string().max(512).nullable().optional(),
}).refine((p) => p.end >= p.start && Array.from(p.text).length === p.end - p.start,
  'Passage text must match its character span');
export const pageSchema = <T extends z.ZodType>(item: T) => z.object({
  items: z.array(item), total: count, limit: count.positive(), offset: count,
});
const lexicalSearchSchema = z.object({
  status: z.enum(['evidence_found', 'insufficient_evidence']),
  mode: z.literal('lexical_excerpts'), answer: z.null(),
  retrieval_version: z.enum(['fts5-overlap-v1', 'postgres-simple-overlap-v1']),
  passages: z.array(passageSchema), candidate_limit: count.positive(),
  truncated: z.boolean(), duration_ms: z.number().nonnegative(),
}).refine((r) => (r.passages.length > 0) === (r.status === 'evidence_found'));
const vectorSearchSchema = z.object({
  status: z.enum(['evidence_found', 'insufficient_evidence']), mode: z.enum(['vector', 'hybrid']),
  passages: z.array(passageSchema), retrieval_version: z.string(),
  embedding_model: z.string(), model_digest: z.string(), dimensions: count.positive(),
  indexed_chunks: count, unindexed_chunks: count, candidate_limit: count.positive(),
  truncated: z.boolean(), duration_ms: z.number().nonnegative(),
  rrf_rank_constant: count.positive().nullable(), fusion_depth: count.positive().nullable(),
}).refine((r) => (r.passages.length > 0) === (r.status === 'evidence_found'));
export const searchSchema = z.union([lexicalSearchSchema, vectorSearchSchema]);
const vectorIndexSchema = z.object({
  document_id: z.string().uuid(), document_version: count.positive(), chunk_count: count.positive(),
  embedding_model: z.string(), model_digest: z.string(), dimensions: count.positive(), index_version: z.string(),
});
export type RetrievalMode = 'lexical' | 'vector' | 'hybrid';
export type Document = z.infer<typeof documentSchema>;
export type Passage = z.infer<typeof passageSchema>;
export type Page<T> = { items: T[]; total: number; offset: number; limit: number };
export type SearchResult = z.infer<typeof searchSchema>;
export const capabilitiesSchema = z.object({
  generation_enabled: z.boolean(), retrieval_modes: z.array(z.enum(['lexical', 'vector', 'hybrid'])),
  backend: z.enum(['sqlite', 'postgres']),
});
export type Capabilities = z.infer<typeof capabilitiesSchema>;
export const answerSchema = z.object({
  answer: z.object({
    status: z.enum(['answered', 'insufficient_evidence', 'conflicting_evidence']),
    claims: z.array(z.object({ text: z.string().min(1).max(2000),
      citation_ids: z.array(z.string().uuid()).min(1).max(5),
      quotes: z.array(z.string().min(1)).min(1).max(5) })).max(8),
    model: z.string(), model_digest: z.string().nullable(), prompt_version: z.string(),
    input_tokens: count.nullable(), output_tokens: count.nullable(), provider_fee_usd: z.literal(0),
    compute_cost_usd: z.null(), grounding_validation: z.literal('verbatim_claims_and_citations'),
  }),
  passages: z.array(passageSchema).max(5), retrieval_version: z.string(), duration_ms: z.number().nonnegative(),
}).refine(({ answer, passages }) => {
  if ((answer.status === 'insufficient_evidence') !== (answer.claims.length === 0)) return false;
  if (answer.status === 'conflicting_evidence' && new Set(answer.claims.flatMap((c) => c.citation_ids)).size < 2) return false;
  const sources = new Map(passages.map((p) => [p.id, p]));
  return answer.claims.every((claim) => claim.text.trim().length > 0 && claim.citation_ids.length === claim.quotes.length
    && claim.citation_ids.every((id, index) => {
      const quote = claim.quotes[index];
      return quote !== undefined && quote.trim().length > 0 && sources.get(id)?.text.includes(quote)
        && sources.get(id)?.text.includes(claim.text);
    }));
}, 'Claims and quotations must resolve to supplied source passages');
export type AnswerResult = z.infer<typeof answerSchema>;

const messages: Record<number, string> = {
  401: 'Access token was rejected. Disconnect and enter a valid token.',
  403: 'You do not have access to this resource.',
  404: 'This source is unavailable. It may have been replaced or deleted. Refresh and search again.',
  408: 'The request timed out. Retry when the server is available.',
  409: 'Sources changed while the answer was being prepared. Run your question again.',
  413: 'This document exceeds the server size limit. Upload a smaller document.',
  415: 'Use PDF, or UTF-8 HTML, Markdown or plain text.',
  422: 'The server rejected this input. Check the document key, text, or question.',
  429: 'The request limit was reached. Wait a minute before retrying.',
};
const parserMessages: Record<string, string> = {
  invalid_pdf: 'This PDF is malformed or exceeds the parser limits. Try a smaller text-based PDF.',
  encrypted_pdf: 'Encrypted PDFs are not supported. Upload an unencrypted copy.',
  empty_document: 'No extractable text was found. Image-only PDFs need OCR first.',
  parser_timeout: 'PDF parsing exceeded its time limit. Try a smaller or simpler PDF.',
  html_complexity_limit: 'This HTML is too complex. Export a simpler HTML or text file.',
  invalid_encoding: 'Text and HTML files must use UTF-8 encoding.',
};

export class Client {
  private readonly session = new AbortController();
  constructor(private readonly token: string) {}
  close() { this.session.abort(); }

  private async request<T>(path: string, schema: z.ZodType<T>, init: RequestInit = {}, timeout = 20000): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`/v1${path}`, {
        ...init,
        headers: { ...init.headers, Authorization: `Bearer ${this.token}` },
        cache: 'no-store', credentials: 'omit', redirect: 'error',
        signal: AbortSignal.any([this.session.signal, AbortSignal.timeout(timeout)]),
      });
    } catch {
      throw new Error('The local API could not be reached or the request timed out. Check the server and retry.');
    }
    if (!response.ok) {
      const failure = z.object({ error: z.object({ code: z.string() }) })
        .safeParse(await response.json().catch(() => null));
      if (failure.success && parserMessages[failure.data.error.code]) {
        throw new Error(parserMessages[failure.data.error.code]);
      }
      throw new Error(messages[response.status] ?? 'The server could not complete this request. Retry shortly.');
    }
    try {
      return schema.parse(response.status === 204 ? undefined : await response.json());
    } catch {
      throw new Error('The API returned an unsupported response. Check that the UI and API versions match.');
    }
  }

  documents(offset: number) { return this.request(`/documents?limit=20&offset=${offset}`, pageSchema(documentSchema)); }
  capabilities() { return this.request('/capabilities', capabilitiesSchema); }
  answer(question: string, mode: RetrievalMode = 'lexical') {
    return this.request(mode === 'lexical' ? '/answers' : `/answers?mode=${mode}`, answerSchema, { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, limit: 5 }) }, 250000);
  }
  chunks(id: string, offset: number) { return this.request(`/documents/${encodeURIComponent(id)}/chunks?limit=20&offset=${offset}`, pageSchema(passageSchema)); }
  citation(id: string) { return this.request(`/citations/${encodeURIComponent(id)}`, passageSchema); }
  upload(key: string, text: string | Blob, media: string) {
    return this.request(`/documents/${encodeURIComponent(key)}`, documentSchema,
      { method: 'PUT', headers: { 'Content-Type': media }, body: text });
  }
  delete(id: string) { return this.request(`/documents/${encodeURIComponent(id)}`, z.undefined(), { method: 'DELETE' }); }
  indexVectors(id: string) {
    return this.request(`/documents/${encodeURIComponent(id)}/vector-index`, vectorIndexSchema,
      { method: 'POST' }, 250000);
  }
  search(question: string, mode: RetrievalMode = 'lexical') {
    return this.request(mode === 'lexical' ? '/search' : `/search?mode=${mode}`, searchSchema, { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, limit: 5 }) }, 130000);
  }
}
