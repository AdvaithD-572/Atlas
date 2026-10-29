import type { AnswerResult } from './api';

export function GroundedAnswer({ result, inspect }: { result: AnswerResult; inspect: (id: string) => void }) {
  const { answer } = result;
  const title = answer.status === 'answered' ? 'Grounded answer'
    : answer.status === 'conflicting_evidence' ? 'Conflicting evidence' : 'Insufficient evidence';
  return <section className="answer" aria-labelledby="answer-title">
    <h3 id="answer-title">{title}</h3>
    {answer.status === 'insufficient_evidence'
      ? <p>The available evidence did not support an answer. Try another question or add a relevant source.</p>
      : <p>These verbatim source claims were selected by the local model. Citation validation checks the source text; it does not prove that a claim is correct or relevant.</p>}
    {answer.status === 'conflicting_evidence' && <p className="warning">Sources disagree. Review the cited versions before drawing a conclusion; Atlas has not resolved the disagreement.</p>}
    <ol className="claims">{answer.claims.map((claim, index) => <li key={index}>
      <p>{claim.text}</p>
      <div className="actions">{claim.citation_ids.map((id, sourceIndex) => {
        const source = result.passages.find((p) => p.id === id);
        return <button key={`${id}-${sourceIndex}`} onClick={() => inspect(id)}>
          Source {sourceIndex + 1}: {source?.source_key} · v{source?.version}
        </button>;
      })}</div>
    </li>)}</ol>
    <details><summary>Answer run details</summary>
      <dl><dt>Local model</dt><dd>{answer.model}</dd>
        <dt>Model digest</dt><dd>{answer.model_digest ?? 'Not available (no model call may have been needed)'}</dd>
        <dt>Prompt version</dt><dd>{answer.prompt_version}</dd>
        <dt>Retrieval version</dt><dd>{result.retrieval_version}</dd>
        <dt>Input / output tokens</dt><dd>{answer.input_tokens ?? 'not reported'} / {answer.output_tokens ?? 'not reported'}</dd>
        <dt>Duration</dt><dd>{(result.duration_ms / 1000).toFixed(2)} seconds</dd>
        <dt>Provider fee</dt><dd>$0; local compute cost is not measured.</dd>
      </dl>
    </details>
  </section>;
}
