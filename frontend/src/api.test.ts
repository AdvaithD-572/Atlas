import { describe, expect, it, vi, afterEach } from 'vitest';
import { Client, searchSchema, passageSchema } from './api';

afterEach(() => vi.unstubAllGlobals());

describe('API boundary', () => {
  it('rejects generated text in an excerpt response', () => {
    expect(() => searchSchema.parse({ status: 'evidence_found', mode: 'lexical_excerpts',
      answer: 'invented answer', passages: [], truncated: false, duration_ms: 1,
      retrieval_version: 'fts5-overlap-v1', candidate_limit: 200 })).toThrow();
  });
  it('rejects malformed passage locations', () => {
    expect(() => passageSchema.parse({ id: 'bad', document_id: 'bad', source_key: 'a',
      version: 1, ordinal: 0, start: -1, end: 4, text: 'text' })).toThrow();
  });
  it('sends the token only in the authorization header and disables caching', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, limit: 20, offset: 0 })));
    vi.stubGlobal('fetch', fetcher);
    await new Client('test-only-token').documents(0);
    expect(fetcher.mock.calls[0]?.[0]).toBe('/v1/documents?limit=20&offset=0');
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({ cache: 'no-store', credentials: 'omit', redirect: 'error',
      headers: { Authorization: 'Bearer test-only-token' } });
  });
  it('replaces internal server errors with a safe actionable message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('sensitive internal detail', { status: 500 })));
    await expect(new Client('test').documents(0)).rejects.toThrow('The server could not complete this request. Retry shortly.');
  });
  it('reports authentication failures without showing server body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('secret', { status: 401 })));
    await expect(new Client('test').documents(0)).rejects.toThrow('Access token was rejected. Disconnect and enter a valid token.');
  });
});
