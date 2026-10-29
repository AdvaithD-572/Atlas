import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { describe, expect, it, vi } from 'vitest';
import { EvaluationReport, reportSchema } from './EvaluationReport';

// Synthetic consumer fixtures only; actual Python serialization has a separate contract test.
function fixture() {
  const unknown = { value: null, count: 0 };
  return {
    evaluator_version: 'atlas-eval-v1', dataset_hash: 'a'.repeat(64), corpus_hash: 'b'.repeat(64),
    config_hash: 'c'.repeat(64), official: false, created_at: '2026-10-20T00:00:00Z',
    config: { mode: 'lexical', k: 5, retrieval_version: 'fts5-overlap-v1', model_id: null,
      model_digest: null, experiment_id: 'synthetic-fixture', corpus_version: 'test', chunking_version: 'test' },
    summary: {
      count: 2, failures: 1, retrieval_recall_at_k: { value: 0.5, count: 1 },
      retrieval_mrr: { value: 0.5, count: 1 }, citation_precision: unknown,
      citation_recall: unknown, answer_correctness: unknown, faithfulness: unknown,
      abstention: { tp: 0, fp: 0, tn: 0, fn: 0, count: 0, precision: null, recall: null, accuracy: null },
      latency_ms: { p50: 10, p95: 20, p99: 20 },
    },
    cases: [{ case_id: 'test-1', failed: false, estimated_cost_usd: null },
      { case_id: 'test-2', failed: true }],
  };
}

function file(value: unknown): File {
  const upload = new File([JSON.stringify(value)], 'results.json', { type: 'application/json' });
  // jsdom lacks Blob.arrayBuffer; only the file-reading boundary is substituted.
  Object.defineProperty(upload, 'arrayBuffer', { value: async () => new TextEncoder().encode(JSON.stringify(value)).buffer });
  return upload;
}

describe('evaluation report viewer', () => {
  it('loads exported metrics without converting missing ratings or costs to zero', async () => {
    const user = userEvent.setup();
    const fetcher = vi.spyOn(globalThis, 'fetch');
    try {
      const { container } = render(<EvaluationReport />);
      expect(screen.getByText(/No evaluation report loaded/)).toBeInTheDocument();
      await user.upload(screen.getByLabelText('Evaluation report JSON'), file(fixture()));
      const table = await screen.findByRole('table', { name: 'Reported evaluation metrics' });
      expect(within(table).getByRole('row', { name: /Recall@5 0.500 1 of 2/ })).toBeInTheDocument();
      expect(within(table).getByRole('row', { name: /Answer correctness Not measured 0 of 2/ })).toBeInTheDocument();
      expect(screen.getByText('Failures: 1 of 2 attempted cases.')).toBeInTheDocument();
      expect(screen.getByText('Retrieval truncation: Not recorded.')).toBeInTheDocument();
      expect(screen.getByText(/Estimated cost: Not measured/)).toBeInTheDocument();
      expect(screen.getByText('Development report')).toBeInTheDocument();
      expect(fetcher).not.toHaveBeenCalled();
      expect((await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })).violations).toEqual([]);
      await user.click(screen.getByRole('button', { name: 'Clear report' }));
      expect(screen.queryByRole('table')).not.toBeInTheDocument();
      expect(screen.getByLabelText('Evaluation report JSON')).toHaveFocus();
    } finally { fetcher.mockRestore(); }
  });

  it('shows candidate truncation separately from failures and preserves missing status', async () => {
    const user = userEvent.setup();
    render(<EvaluationReport />);
    const payload = fixture();
    const cases = payload.cases.map(item => ({ ...item, truncated: true }));
    await user.upload(screen.getByLabelText('Evaluation report JSON'), file({ ...payload, cases }));
    expect(await screen.findByText('Retrieval truncation: 1 of 1 recorded cases.')).toBeInTheDocument();
    expect(screen.getByText(/Candidate limits excluded some passages/)).toBeInTheDocument();
    expect(screen.getByText('Unrecorded truncation status: 0 successful cases.')).toBeInTheDocument();
    await user.upload(screen.getByLabelText('Evaluation report JSON'), file({
      ...payload, cases: cases.map(item => ({ ...item, truncated: false })),
    }));
    expect(await screen.findByText('Retrieval truncation: 0 of 1 recorded cases.')).toBeInTheDocument();
    expect(screen.queryByText(/Candidate limits excluded some passages/)).not.toBeInTheDocument();
  });

  it('clears stale results on invalid input and allows another selection', async () => {
    const user = userEvent.setup();
    render(<EvaluationReport />);
    await user.upload(screen.getByLabelText('Evaluation report JSON'), file(fixture()));
    await screen.findByRole('table');
    await user.upload(screen.getByLabelText('Evaluation report JSON'), file({ secret: 'never display raw input' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose a valid Atlas evaluation report');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByText(/never display raw input/)).not.toBeInTheDocument();
    await user.upload(screen.getByLabelText('Evaluation report JSON'), file(fixture()));
    expect(await screen.findByRole('table')).toBeInTheDocument();
  });

  it('rejects oversized files before reading and ignores a cleared pending read', async () => {
    const user = userEvent.setup();
    render(<EvaluationReport />);
    const huge = file(fixture());
    Object.defineProperty(huge, 'size', { value: 10 * 1024 * 1024 + 1 });
    await user.upload(screen.getByLabelText('Evaluation report JSON'), huge);
    expect(await screen.findByRole('alert')).toHaveTextContent('10 MiB');
    let release!: (value: ArrayBuffer) => void;
    const pending = new File(['{}'], 'pending.json');
    Object.defineProperty(pending, 'arrayBuffer', { value: () => new Promise<ArrayBuffer>(resolve => { release = resolve; }) });
    await user.upload(screen.getByLabelText('Evaluation report JSON'), pending);
    expect(screen.getByText('Reading report…')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clear report' }));
    release(new TextEncoder().encode(JSON.stringify(fixture())).buffer);
    await waitFor(() => expect(screen.queryByRole('table')).not.toBeInTheDocument());
  });

  it('rejects inconsistent metric counts, non-finite numbers and unsupported versions', () => {
    const mismatched = fixture();
    mismatched.summary.failures = 0;
    expect(reportSchema.safeParse(mismatched).success).toBe(false);
    const unknown = fixture();
    unknown.summary.citation_precision = { value: null, count: 1 };
    expect(reportSchema.safeParse(unknown).success).toBe(false);
    const nonfinite = fixture();
    nonfinite.summary.latency_ms.p95 = Infinity;
    expect(reportSchema.safeParse(nonfinite).success).toBe(false);
    expect(reportSchema.safeParse({ ...fixture(), evaluator_version: 'unknown' }).success).toBe(false);
  });

  it('renders report labels as text and does not certify a declared official flag', async () => {
    const user = userEvent.setup();
    render(<EvaluationReport />);
    const payload = fixture();
    payload.official = true;
    payload.config.experiment_id = '<img src=x onerror=alert(1)>';
    await user.upload(screen.getByLabelText('Evaluation report JSON'), file(payload));
    expect(await screen.findByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByText('Report declares official benchmark status')).toBeInTheDocument();
    expect(screen.getByText(/does not independently verify/)).toBeInTheDocument();
  });
});
