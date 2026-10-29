import { useEffect, useRef, useState } from 'react';
import { z } from 'zod';

const count = z.number().int().min(0).max(10000);
const score = z.number().min(0).max(1).nullable();
const digest = z.string().regex(/^[a-f0-9]{64}$/);
const label = z.string().min(1).max(120);
const metric = z.object({ value: score, count }).refine(value => (value.count === 0) === (value.value === null));
const metricKeys = ['retrieval_recall_at_k', 'retrieval_mrr', 'citation_precision', 'citation_recall', 'answer_correctness', 'faithfulness'] as const;

// Consumer projection of atlas.evaluation.run_experiment (atlas-eval-v1).
// Real serialized reports are checked in provider.contract.ts; unused fields are discarded.
export const reportSchema = z.object({
  evaluator_version: z.literal('atlas-eval-v1'),
  dataset_hash: digest, corpus_hash: digest, config_hash: digest,
  official: z.boolean(), created_at: z.iso.datetime({ offset: true }),
  config: z.object({
    mode: z.enum(['lexical', 'vector', 'hybrid']), k: z.number().int().min(1).max(20),
    retrieval_version: z.enum(['fts5-overlap-v1', 'postgres-simple-overlap-v1', 'cosine-exact-v1', 'rrf60-depth20-v1']),
    model_id: z.string().min(1).max(512).nullable(), model_digest: digest.nullable(),
    experiment_id: label, corpus_version: label, chunking_version: label,
    generate_answers: z.boolean().optional().default(false),
    generation_model_id: z.string().min(1).max(100).nullable().optional().default(null),
    generation_model_digest: digest.nullable().optional().default(null),
    prompt_version: label.nullable().optional().default(null),
  }),
  summary: z.object({
    count: count.min(1), failures: count,
    retrieval_recall_at_k: metric, retrieval_mrr: metric, citation_precision: metric,
    citation_recall: metric, answer_correctness: metric, faithfulness: metric,
    latency_ms: z.object({ p50: z.number().nonnegative(), p95: z.number().nonnegative(), p99: z.number().nonnegative() }),
    abstention: z.object({ tp: count, fp: count, tn: count, fn: count, count, precision: score, recall: score, accuracy: score }),
  }),
  cases: z.array(z.object({
    case_id: label, failed: z.boolean(),
    truncated: z.boolean().optional(),
    estimated_cost_usd: z.number().nonnegative().max(Number.MAX_SAFE_INTEGER).nullable().optional(),
    input_tokens: z.number().int().nonnegative().nullable().optional(),
    output_tokens: z.number().int().nonnegative().nullable().optional(),
  })).min(1).max(10000),
}).superRefine((report, ctx) => {
  const { summary: s, cases, config: c } = report;
  const successful = s.count - s.failures;
  const a = s.abstention;
  const validMode = c.mode === 'lexical'
    ? ['fts5-overlap-v1', 'postgres-simple-overlap-v1'].includes(c.retrieval_version) && c.model_id === null && c.model_digest === null
    : c.retrieval_version === (c.mode === 'vector' ? 'cosine-exact-v1' : 'rrf60-depth20-v1') && c.model_id !== null && c.model_digest !== null;
  const validGeneration = c.generate_answers
    ? c.generation_model_id !== null && c.generation_model_digest !== null && c.prompt_version !== null && c.k <= 5
    : c.generation_model_id === null && c.generation_model_digest === null && c.prompt_version === null;
  if (!validMode || !validGeneration || s.count !== cases.length || s.failures !== cases.filter(item => item.failed).length ||
      new Set(cases.map(item => item.case_id)).size !== cases.length ||
      metricKeys.some(key => s[key].count > successful) ||
      a.count > successful || a.count !== a.tp + a.fp + a.tn + a.fn ||
      (a.count === 0) !== (a.accuracy === null) ||
      s.latency_ms.p50 > s.latency_ms.p95 || s.latency_ms.p95 > s.latency_ms.p99) {
    ctx.addIssue({ code: 'custom', message: 'Inconsistent evaluation report' });
  }
});
type Report = z.infer<typeof reportSchema>;

function valueText(value: number | null) { return value === null ? 'Not measured' : value.toFixed(3); }

export function EvaluationReport() {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const generation = useRef(0);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => () => { generation.current += 1; }, []);

  async function load(file: File | undefined) {
    if (!file) return;
    const current = ++generation.current;
    setReport(null); setError(''); setLoading(true);
    try {
      if (file.size > 10 * 1024 * 1024) {
        setError('Choose a report no larger than 10 MiB.'); return;
      }
      const text = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
      if (generation.current !== current) return;
      setReport(reportSchema.parse(JSON.parse(text)));
    } catch {
      if (generation.current === current) setError('Choose a valid Atlas evaluation report (results.json, evaluator atlas-eval-v1).');
    } finally {
      if (generation.current === current) setLoading(false);
    }
  }
  function clear() {
    generation.current += 1;
    setReport(null); setError(''); setLoading(false);
    if (input.current) { input.current.value = ''; input.current.focus(); }
  }
  const costs = report?.cases.filter(item => !item.failed && item.estimated_cost_usd != null) ?? [];
  const costSum = costs.reduce((total, item) => total + (item.estimated_cost_usd ?? 0), 0);
  const truncation = report?.cases.filter(item => !item.failed && item.truncated !== undefined) ?? [];
  const truncated = truncation.filter(item => item.truncated).length;
  const labels = report ? [`Recall@${report.config.k}`, `MRR@${report.config.k}`, 'Citation precision', 'Citation recall', 'Answer correctness', 'Faithfulness'] : [];

  return <section aria-labelledby="evaluation-title">
    <h2 id="evaluation-title">Evaluation results</h2>
    <p id="report-help">Open an exported Atlas results.json to inspect its metrics. The file stays in this page’s memory and is cleared on disconnect. It is not uploaded.</p>
    <label htmlFor="evaluation-report">Evaluation report JSON</label>
    <input ref={input} id="evaluation-report" type="file" accept=".json,application/json"
      aria-describedby={`report-help${error ? ' report-error' : ''}`} aria-invalid={!!error}
      onChange={event => { void load(event.target.files?.[0]); event.target.value = ''; }} />
    <p role="status" aria-label="Evaluation report status">{loading ? 'Reading report…' : report ? 'Report loaded.' : 'No evaluation report loaded.'}</p>
    {error && <p className="error" role="alert" id="report-error">{error}</p>}
    {(report || loading || error) && <button onClick={clear}>Clear report</button>}
    {report && <div className="report">
      <h3>{report.official ? 'Report declares official benchmark status' : 'Development report'}</h3>
      <p className="warning">Metrics and review status come from the selected file. This viewer does not independently verify the experiment or human review.</p>
      <p>{report.config.mode} · {report.config.experiment_id} · {report.created_at}</p>
      <p>{report.config.generate_answers ? 'Retrieval and generated-answer outcomes' : 'Retrieval-only run'}</p>
      <p>Failures: {report.summary.failures} of {report.summary.count} attempted cases.</p>
      <p>Retrieval truncation: {truncation.length ? `${truncated} of ${truncation.length} recorded cases.` : 'Not recorded.'}</p>
      {truncation.length > 0 && <p className="subtle">Unrecorded truncation status: {report.summary.count - report.summary.failures - truncation.length} successful cases.</p>}
      {truncated > 0 && <p className="warning">Candidate limits excluded some passages. Interpret retrieval scores with this limitation.</p>}
      <table>
        <caption>Reported evaluation metrics</caption>
        <thead><tr><th scope="col">Metric</th><th scope="col">Value</th><th scope="col">Scored cases</th></tr></thead>
        <tbody>
          {metricKeys.map((key, index) => <tr key={key}>
            <th scope="row">{labels[index]}</th><td>{valueText(report.summary[key].value)}</td>
            <td>{report.summary[key].count} of {report.summary.count}</td>
          </tr>)}
          {(['precision', 'recall', 'accuracy'] as const).map(key => <tr key={key}>
            <th scope="row">Abstention {key}</th><td>{valueText(report.summary.abstention[key])}</td>
            <td>{report.summary.abstention.count} of {report.summary.count}</td>
          </tr>)}
        </tbody>
      </table>
      <p className="subtle">Means exclude unmeasured and failed cases. Citation overlap measures passage IDs, not semantic support. Abstention scores require explicit answer outcomes.</p>
      <p>Latency: p50 {report.summary.latency_ms.p50.toFixed(3)} ms · p95 {report.summary.latency_ms.p95.toFixed(3)} ms · p99 {report.summary.latency_ms.p99.toFixed(3)} ms</p>
      <p>Estimated cost: {costs.length ? `$${costSum.toFixed(6)} across ${costs.length} of ${report.summary.count} cases; other costs are unknown.` : 'Not measured.'}</p>
      <details><summary>Recorded configuration and hashes</summary><dl>
        <dt>Retrieval version</dt><dd>{report.config.retrieval_version}</dd>
        <dt>Embedding model</dt><dd>{report.config.model_id ?? 'No embedding model'}</dd>
        <dt>Model digest</dt><dd>{report.config.model_digest ?? 'Not applicable'}</dd>
        {report.config.generate_answers && <>
          <dt>Generation model</dt><dd>{report.config.generation_model_id}</dd>
          <dt>Generation digest</dt><dd>{report.config.generation_model_digest}</dd>
          <dt>Prompt version</dt><dd>{report.config.prompt_version}</dd>
        </>}
        <dt>Corpus version</dt><dd>{report.config.corpus_version}</dd>
        <dt>Chunking version</dt><dd>{report.config.chunking_version}</dd>
        <dt>Dataset SHA256</dt><dd>{report.dataset_hash}</dd>
        <dt>Corpus SHA256</dt><dd>{report.corpus_hash}</dd>
        <dt>Configuration SHA256</dt><dd>{report.config_hash}</dd>
      </dl></details>
    </div>}
  </section>;
}
