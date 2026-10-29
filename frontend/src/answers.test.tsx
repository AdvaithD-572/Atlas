import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { answerSchema, type AnswerResult } from './api';

// Deliberately synthetic API fixtures; these are not model-quality evidence.
const source = {
  id: '11111111-1111-4111-8111-111111111111', document_id: '22222222-2222-4222-8222-222222222222',
  source_key: 'manual.md', version: 1, ordinal: 0, start: 0, end: 19, text: 'Retention: 30 days.',
};
const claim = { text: source.text, citation_ids: [source.id], quotes: [source.text] };
const result: AnswerResult = {
  answer: { status: 'answered', claims: [claim], model: 'synthetic-test-model', model_digest: 'fixture-digest',
    prompt_version: 'extractive-grounding-v1', input_tokens: 10, output_tokens: 5,
    provider_fee_usd: 0, compute_cost_usd: null, grounding_validation: 'verbatim_claims_and_citations' },
  passages: [source], retrieval_version: 'fts5-overlap-v1', duration_ms: 100,
};
function json(value: unknown) { return new Response(JSON.stringify(value)); }
afterEach(() => vi.unstubAllGlobals());

async function ask(answer: unknown = result, enabled = true) {
  const fetcher = vi.fn<typeof fetch>(async (path) => {
    if (path === '/v1/documents?limit=20&offset=0') return json({ items: [], total: 0, limit: 20, offset: 0 });
    if (path === '/v1/capabilities') return json({ generation_enabled: enabled, retrieval_modes: ['lexical'], backend: 'sqlite' });
    if (path === '/v1/answers') return json(answer);
    if (path === `/v1/citations/${source.id}`) return json(source);
    throw new Error('Unexpected test request');
  });
  vi.stubGlobal('fetch', fetcher);
  const view = render(<App />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Access token'), 'synthetic-test-token');
  await user.click(screen.getByRole('button', { name: 'Connect' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Find passages' })).toBeEnabled());
  if (enabled) {
    await user.selectOptions(screen.getByLabelText('Response mode'), 'answer');
    await user.type(screen.getByLabelText('Question or search terms'), 'How long is retention?');
    await user.click(screen.getByRole('button', { name: 'Ask local model' }));
  }
  return { user, fetcher, ...view };
}

describe('grounded answers', () => {
  it('offers generation only when the authenticated capabilities enable it', async () => {
    await ask(result, false);
    expect(screen.queryByRole('option', { name: /Grounded answer/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Ask local model' })).not.toBeInTheDocument();
  });
  it('renders verbatim claims with exact source inspection, metadata and accessible controls', async () => {
    const { user, fetcher, container } = await ask();
    expect(await screen.findByRole('heading', { name: 'Grounded answer' })).toBeInTheDocument();
    expect(screen.getByText(source.text)).toBeInTheDocument();
    expect(screen.getByText(/does not prove that a claim is correct/)).toBeInTheDocument();
    const sourceButton = screen.getByRole('button', { name: 'Source 1: manual.md · v1' });
    await user.click(sourceButton);
    expect(await screen.findByRole('heading', { name: 'Source inspection' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Close source inspection' }));
    expect(sourceButton).toHaveFocus();
    expect(fetcher.mock.calls.find(([url]) => url === '/v1/answers')?.[1]).toMatchObject({
      method: 'POST', body: JSON.stringify({ question: 'How long is retention?', limit: 5 }),
    });
    expect((await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })).violations).toEqual([]);
  });
  it('shows model abstention without manufacturing a claim', async () => {
    await ask({ ...result, answer: { ...result.answer, status: 'insufficient_evidence', claims: [], model_digest: null } });
    expect(await screen.findByRole('heading', { name: 'Insufficient evidence' })).toBeInTheDocument();
    expect(screen.queryByText(source.text)).not.toBeInTheDocument();
  });
  it('makes conflicting sources explicit and does not invent a resolution', async () => {
    const other = { ...source, id: '33333333-3333-4333-8333-333333333333', source_key: 'older.md', text: 'Retention: 90 days.' };
    await ask({ ...result, passages: [source, other], answer: { ...result.answer, status: 'conflicting_evidence',
      claims: [claim, { text: other.text, citation_ids: [other.id], quotes: [other.text] }] } });
    expect(await screen.findByRole('heading', { name: 'Conflicting evidence' })).toBeInTheDocument();
    expect(screen.getByText(/has not resolved the disagreement/)).toBeInTheDocument();
  });
  it('rejects unsupported claims or mismatched citations instead of rendering them', async () => {
    await ask({ ...result, answer: { ...result.answer, claims: [{ ...claim, text: 'Unsupported private data.' }] } });
    expect(await screen.findByRole('alert')).toHaveTextContent('unsupported response');
    expect(screen.queryByText('Unsupported private data.')).not.toBeInTheDocument();
    expect(() => answerSchema.parse({ ...result, passages: [] })).toThrow();
    expect(() => answerSchema.parse({ ...result, answer: { ...result.answer, status: 'conflicting_evidence' } })).toThrow();
  });
});
