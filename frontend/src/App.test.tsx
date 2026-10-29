import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

// Explicit synthetic HTTP fixtures for isolated component tests, not demo data.
const document = {
  id: '11111111-1111-4111-8111-111111111111', source_key: 'guide.md', version: 1,
  status: 'indexed', chunk_count: 1, media_type: 'text/markdown', content_hash: 'test-hash',
  parser_version: 'text-v1', chunk_size: 800, chunk_overlap: 120,
  normalization: 'none-v1', embedding_model: null, created_at: '2026-10-19T00:00:00Z', updated_at: '2026-10-19T00:00:00Z',
};
const passage = {
  id: '22222222-2222-4222-8222-222222222222', document_id: document.id,
  source_key: document.source_key, version: 1, ordinal: 0, start: 0, end: 29,
  text: 'Atlas preserves source spans.',
};
function page(items: unknown[], total = items.length, offset = 0) { return { items, total, offset, limit: 20 }; }
function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status }); }
const fetcher = vi.fn<typeof fetch>();

beforeEach(() => {
  fetcher.mockReset();
  fetcher.mockImplementation(async () => { throw new Error('Unexpected request in component test'); });
  vi.stubGlobal('fetch', (path: string, init?: RequestInit) => path === '/v1/capabilities'
    ? Promise.resolve(response({ generation_enabled: false, retrieval_modes: ['lexical'], backend: 'sqlite' }))
    : fetcher(path, init));
});
afterEach(() => vi.unstubAllGlobals());

async function connect() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Access token'), 'test-only-access-token');
  await user.click(screen.getByRole('button', { name: 'Connect' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh documents' })).toBeEnabled());
  return user;
}

describe('document workspace', () => {
  it('uploads a PDF without decoding or editing its binary bytes', async () => {
    fetcher.mockResolvedValueOnce(response(page([])))
      .mockResolvedValueOnce(response({ ...document, source_key: 'guide.pdf', media_type: 'application/pdf' }, 201))
      .mockResolvedValueOnce(response(page([])));
    render(<App />);
    const user = await connect();
    const file = new File(['%PDF-synthetic-ui-test'], 'guide.pdf', { type: 'application/pdf' });
    await user.upload(screen.getByLabelText('Choose a document file'), file);
    expect(await screen.findByText(/PDF selected: guide.pdf/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Document text')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Index document' }));
    expect(await screen.findByText(/guide.pdf indexed/)).toBeInTheDocument();
    expect(fetcher.mock.calls[1]?.[1]).toMatchObject({ body: file, headers: { 'Content-Type': 'application/pdf' } });
  });

  it('shows PDF page and HTML heading locations as plain text', async () => {
    fetcher.mockResolvedValueOnce(response(page([document])))
      .mockResolvedValueOnce(response(page([{ ...passage, page_number: 3, heading: '<b>Setup</b>' }])));
    render(<App />);
    const user = await connect();
    await user.click(screen.getByRole('button', { name: 'View passages' }));
    expect(await screen.findByText(/Page 3/)).toBeInTheDocument();
    expect(screen.getByText(/Heading: <b>Setup<\/b>/)).toBeInTheDocument();
  });
  it('does not fetch before connection and stores no token in browser storage', async () => {
    render(<App />);
    expect(fetcher).not.toHaveBeenCalled();
    fetcher.mockResolvedValueOnce(response(page([])));
    const user = await connect();
    expect(screen.getByText(/No documents on this page/)).toBeInTheDocument();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    await user.click(screen.getByRole('button', { name: 'Disconnect' }));
    expect(screen.getByLabelText('Access token')).toHaveValue('');
    expect(screen.queryByRole('heading', { name: 'Your documents' })).not.toBeInTheDocument();
  });

  it('indexes real entered text with a stable key and displays API metadata', async () => {
    fetcher.mockResolvedValueOnce(response(page([])))
      .mockResolvedValueOnce(response(document, 201))
      .mockResolvedValueOnce(response(page([document])));
    render(<App />);
    const user = await connect();
    await user.type(screen.getByLabelText('Document key'), 'guide.md');
    await user.selectOptions(screen.getByLabelText('Format'), 'text/markdown');
    await user.type(screen.getByLabelText('Document text'), '# Atlas\nSource text.');
    await user.click(screen.getByRole('button', { name: 'Index document' }));
    expect(await screen.findByText(/guide.md indexed. Version 1/)).toBeInTheDocument();
    expect(fetcher.mock.calls[1]?.[0]).toBe('/v1/documents/guide.md');
    expect(fetcher.mock.calls[1]?.[1]).toMatchObject({ method: 'PUT', body: '# Atlas\nSource text.',
      headers: { 'Content-Type': 'text/markdown' } });
    expect(screen.getByLabelText('Document text')).toHaveValue('');
    await user.click(screen.getByRole('button', { name: 'Replace' }));
    expect(screen.getByLabelText('Document key')).toHaveValue('guide.md');
    expect(screen.getByText(/Replacement key selected/)).toBeInTheDocument();
  });

  it('searches excerpts and fetches the exact citation under authentication', async () => {
    fetcher.mockResolvedValueOnce(response(page([document])))
      .mockResolvedValueOnce(response({ status: 'evidence_found', mode: 'lexical_excerpts', answer: null,
        retrieval_version: 'fts5-overlap-v1', passages: [passage], truncated: true, candidate_limit: 200, duration_ms: 1.2 }))
      .mockResolvedValueOnce(response(passage));
    render(<App />);
    const user = await connect();
    await user.type(screen.getByLabelText('Question or search terms'), 'source spans');
    await user.click(screen.getByRole('button', { name: 'Find passages' }));
    expect(await screen.findByRole('heading', { name: 'Retrieved source excerpts' })).toBeInTheDocument();
    expect(screen.getByText(/Results may be incomplete/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Inspect source passage 1' }));
    const heading = await screen.findByRole('heading', { name: 'Source inspection' });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(fetcher.mock.calls[2]?.[0]).toBe(`/v1/citations/${passage.id}`);
    expect(screen.getAllByText(passage.text)).toHaveLength(2);
  });

  it('shows insufficient evidence without a fabricated answer', async () => {
    fetcher.mockResolvedValueOnce(response(page([])))
      .mockResolvedValueOnce(response({ status: 'insufficient_evidence', mode: 'lexical_excerpts', answer: null,
        retrieval_version: 'fts5-overlap-v1', passages: [], truncated: false, candidate_limit: 200, duration_ms: 0.1 }));
    render(<App />);
    const user = await connect();
    await user.type(screen.getByLabelText('Question or search terms'), 'unknown');
    await user.click(screen.getByRole('button', { name: 'Find passages' }));
    expect(await screen.findByText(/No answer was generated/)).toBeInTheDocument();
  });

  it('does not display stale source text after citation denial', async () => {
    fetcher.mockResolvedValueOnce(response(page([document])))
      .mockResolvedValueOnce(response(page([passage])))
      .mockResolvedValueOnce(new Response(null, { status: 404 }));
    render(<App />);
    const user = await connect();
    await user.click(screen.getByRole('button', { name: 'View passages' }));
    await user.click(await screen.findByRole('button', { name: 'Inspect source passage 1' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This source is unavailable');
    expect(screen.queryByRole('heading', { name: 'Source inspection' })).not.toBeInTheDocument();
  });

  it('requires explicit delete confirmation and refreshes after deletion', async () => {
    fetcher.mockResolvedValueOnce(response(page([document])))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(response(page([])));
    render(<App />);
    const user = await connect();
    await user.click(screen.getByRole('button', { name: /^Delete$/ }));
    expect(fetcher).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'Confirm delete' }));
    expect(await screen.findByText(/deleted, including indexed passages/)).toBeInTheDocument();
    expect(fetcher.mock.calls[1]?.[1]?.method).toBe('DELETE');
    expect(screen.queryByRole('heading', { name: 'guide.md' })).not.toBeInTheDocument();
  });

  it('paginates documents with bounded offsets', async () => {
    fetcher.mockResolvedValueOnce(response(page([document], 21)))
      .mockResolvedValueOnce(response(page([{ ...document, source_key: 'last.md' }], 21, 20)));
    render(<App />);
    const user = await connect();
    await user.click(within(screen.getByRole('navigation', { name: 'Document pages' })).getByRole('button', { name: 'Next' }));
    expect(await screen.findByRole('heading', { name: 'last.md' })).toBeInTheDocument();
    expect(fetcher.mock.calls[1]?.[0]).toBe('/v1/documents?limit=20&offset=20');
  });

  it('can retry a failed list request', async () => {
    fetcher.mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(response(page([])));
    render(<App />);
    const user = await connect();
    expect(screen.getByRole('alert')).toHaveTextContent('Retry shortly');
    await user.click(screen.getByRole('button', { name: 'Retry last operation' }));
    expect(await screen.findByText(/No documents on this page/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('does not restore previous-owner results when an old request completes after disconnect', async () => {
    let complete!: (value: Response) => void;
    fetcher.mockImplementationOnce(() => new Promise((resolve) => { complete = resolve; }));
    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Access token'), 'first-owner');
    await user.click(screen.getByRole('button', { name: 'Connect' }));
    expect(screen.getByRole('status', { name: 'Workspace activity' })).toHaveTextContent('Working');
    await user.click(screen.getByRole('button', { name: 'Disconnect' }));
    fetcher.mockResolvedValueOnce(response(page([])));
    await connect();
    await act(async () => { complete(response(page([document]))); });
    expect(screen.queryByRole('heading', { name: 'guide.md' })).not.toBeInTheDocument();
  });

  it('renders untrusted markup as text and has no axe structural violations', async () => {
    fetcher.mockResolvedValueOnce(response(page([document])))
      .mockResolvedValueOnce(response(page([{ ...passage, text: '<script>bad()</script>', end: 22 }])));
    const { container } = render(<App />);
    expect((await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })).violations).toEqual([]);
    const user = await connect();
    await user.click(screen.getByRole('button', { name: 'View passages' }));
    expect(await screen.findByText('<script>bad()</script>')).toBeInTheDocument();
    expect((await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })).violations).toEqual([]);
  });
});
