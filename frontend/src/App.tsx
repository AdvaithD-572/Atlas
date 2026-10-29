import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Client, type AnswerResult, type Capabilities, type Document, type Page, type Passage, type SearchResult, type RetrievalMode } from './api';
import { GroundedAnswer } from './GroundedAnswer';
import { EvaluationReport } from './EvaluationReport';

function Pager({ page, busy, label, onPage }: {
  page: Page<unknown>; busy: boolean; label: string; onPage: (offset: number) => void;
}) {
  return <nav aria-label={label} className="actions">
    <button disabled={busy || page.offset === 0} onClick={() => onPage(Math.max(0, page.offset - page.limit))}>Previous</button>
    <span>{page.total === 0 ? '0 items' : `${page.offset + 1}–${Math.min(page.offset + page.items.length, page.total)} of ${page.total}`}</span>
    <button disabled={busy || page.offset + page.limit >= page.total || page.offset + page.limit > 100000}
      onClick={() => onPage(page.offset + page.limit)}>Next</button>
  </nav>;
}

function Excerpt({ passage, onInspect }: { passage: Passage; onInspect?: (id: string) => void }) {
  return <article className="excerpt">
    <h3>{passage.source_key} <span className="subtle">· version {passage.version}</span></h3>
    <p className="subtle">Passage {passage.ordinal + 1} · characters {passage.start}–{passage.end} (end exclusive)</p>
    {passage.page_number && <p className="subtle">Page {passage.page_number} · extracted text</p>}
    {passage.heading && <p className="subtle">Heading: {passage.heading}</p>}
    <pre>{passage.text}</pre>
    {onInspect && <button onClick={() => onInspect(passage.id)}>Inspect source passage {passage.ordinal + 1}</button>}
  </article>;
}

export function App() {
  const [draft, setDraft] = useState('');
  const [token, setToken] = useState('');
  function connect(event: FormEvent) {
    event.preventDefault();
    if (draft.trim()) { setToken(draft.trim()); setDraft(''); }
  }
  return <>
    <a className="skip" href="#main">Skip to workspace</a>
    <header><div><p className="eyebrow">Grounded knowledge workspace</p><h1>Atlas</h1></div>
      <span className="badge">Local preview</span></header>
    <main id="main">
      {!token ? <section className="connect" aria-labelledby="connect-title">
        <h2 id="connect-title">Connect to your documents</h2>
        <p>Enter your local Atlas access token. It stays in this page’s memory and is cleared when you disconnect or reload.</p>
        <form onSubmit={connect}>
          <label htmlFor="token">Access token</label>
          <input id="token" type="password" required autoComplete="off" spellCheck={false}
            value={draft} onChange={(e) => setDraft(e.target.value)} />
          <button type="submit">Connect</button>
        </form>
      </section> : <Workspace key={token} token={token} disconnect={() => setToken('')} />}
    </main>
    <footer>Atlas local preview. Local models and semantic retrieval depend on server configuration. Quality benchmark results are not yet available.</footer>
  </>;
}

function Workspace({ token, disconnect }: { token: string; disconnect: () => void }) {
  const [client] = useState(() => new Client(token));
  const [documents, setDocuments] = useState<Page<Document> | null>(null);
  const [selected, setSelected] = useState<Document | null>(null);
  const [chunks, setChunks] = useState<Page<Passage> | null>(null);
  const [citation, setCitation] = useState<Passage | null>(null);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [answer, setAnswer] = useState<AnswerResult | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [mode, setMode] = useState<'excerpts' | 'answer'>('excerpts');
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>('lexical');
  const [key, setKey] = useState('');
  const [content, setContent] = useState('');
  const [media, setMedia] = useState('text/plain');
  const [pdf, setPdf] = useState<File | null>(null);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pendingDelete, setPendingDelete] = useState<Document | null>(null);
  const sourceHeading = useRef<HTMLHeadingElement>(null);
  const sourceTrigger = useRef<HTMLElement | null>(null);
  const retry = useRef<(() => Promise<void>) | null>(null);

  async function run(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice(''); retry.current = action;
    try { await action(); retry.current = null; }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'The request failed. Please retry.'); }
    finally { setBusy(false); }
  }
  async function loadDocuments(offset = 0) {
    setDocuments(null);
    const page = await client.documents(offset);
    setDocuments(page);
  }
  useEffect(() => {
    void run(async () => { await loadDocuments(); setCapabilities(await client.capabilities()); });
    return () => client.close();
    // Client lifetime matches this authenticated workspace's mount.
  }, [client]);
  useEffect(() => { if (citation) sourceHeading.current?.focus(); }, [citation]);

  function clearEvidence() { setCitation(null); setChunks(null); setSelected(null); setResult(null); setAnswer(null); }
  function inspect(id: string) {
    sourceTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setCitation(null);
    void run(async () => { setCitation(await client.citation(id)); });
  }
  function inspectDocument(document: Document, offset = 0) {
    setSelected(document); setChunks(null); setCitation(null);
    void run(async () => { setChunks(await client.chunks(document.id, offset)); });
  }
  async function readFile(file: File | undefined) {
    if (!file) return;
    await run(async () => {
      if (!/\.(txt|md|markdown|html|htm|pdf)$/i.test(file.name)) throw new Error('Choose a PDF, HTML, Markdown or plain text file.');
      if (file.size > 1048576) throw new Error('Choose a file smaller than 1 MiB. Your server may enforce a lower limit.');
      if (/\.pdf$/i.test(file.name)) {
        setPdf(file); setMedia('application/pdf'); setContent('');
        if (!key) setKey(file.name.replace(/[^a-zA-Z0-9_.-]/g, '-').replace(/^[^a-zA-Z0-9]+/, '').slice(0, 120) || 'document');
        setNotice(`PDF selected: ${file.name}. Choose Index document to extract its text.`);
        return;
      }
      let text: string;
      try { text = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()); }
      catch { throw new Error('This file is not valid UTF-8 text. Save it as UTF-8 and retry.'); }
      setContent(text);
      setPdf(null);
      setMedia(/\.(md|markdown)$/i.test(file.name) ? 'text/markdown' : /\.html?$/i.test(file.name) ? 'text/html' : 'text/plain');
      if (!key) setKey(file.name.replace(/[^a-zA-Z0-9_.-]/g, '-').replace(/^[^a-zA-Z0-9]+/, '').slice(0, 120) || 'document');
      setNotice('File loaded into the editor. Review it, then choose Index document.');
    });
  }
  function upload(event: FormEvent) {
    event.preventDefault();
    clearEvidence();
    void run(async () => {
      if (media === 'application/pdf' && !pdf) throw new Error('Choose a PDF file first.');
      const document = await client.upload(key, media === 'application/pdf' && pdf ? pdf : content, media);
      setContent(''); setPdf(null);
      await loadDocuments();
      setNotice(`${document.source_key} indexed. Version ${document.version}, ${document.chunk_count} passages. Unchanged content keeps the same version.`);
    });
  }
  function remove(document: Document) {
    clearEvidence();
    void run(async () => {
      await client.delete(document.id);
      setPendingDelete(null);
      await loadDocuments();
      setNotice(`${document.source_key} deleted, including indexed passages.`);
    });
  }

  return <>
    <div className="session"><p>Authenticated workspace · access checked by the API</p>
      <button onClick={() => { client.close(); disconnect(); }}>Disconnect</button></div>
    <div className="feedback" aria-live="polite" role="status" aria-label="Workspace activity">{busy ? 'Working…' : notice}</div>
    {error && <div className="error" role="alert"><p>{error}</p>
      <button disabled={busy} onClick={() => { const action = retry.current; if (action) void run(action); }}>Retry last operation</button></div>}
    <fieldset className="workspace" disabled={busy} aria-busy={busy}>
      <legend className="sr-only">Document and retrieval workspace</legend>
      <div className="columns">
        <section aria-labelledby="upload-title">
          <h2 id="upload-title">Index a document</h2>
          <p>Upload a text-based PDF, UTF-8 HTML, Markdown or plain text. Scanned PDFs need OCR first. HTML scripts are ignored.</p>
          <form onSubmit={upload}>
            <label htmlFor="file">Choose a document file</label>
            <input id="file" type="file" accept=".txt,.md,.markdown,.html,.htm,.pdf,text/plain,text/markdown,text/html,application/pdf"
              onChange={(e) => { void readFile(e.target.files?.[0]); e.target.value = ''; }} />
            <label htmlFor="key">Document key</label>
            <input id="key" value={key} onChange={(e) => setKey(e.target.value)} required
              pattern="[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,119}" maxLength={120} aria-describedby="key-help" />
            <p id="key-help" className="subtle">Start with a letter or number. Use letters, numbers, dots, hyphens, or underscores. Reusing a key replaces that document and invalidates its old citations.</p>
            <label htmlFor="format">Format</label>
            <select id="format" value={media} onChange={(e) => { setMedia(e.target.value); setPdf(null); }}>
              <option value="text/plain">Plain text</option><option value="text/markdown">Markdown</option>
              <option value="text/html">HTML</option><option value="application/pdf">PDF file</option>
            </select>
            {media === 'application/pdf' ? <p>{pdf ? `Ready to upload: ${pdf.name}` : 'Choose a PDF file above.'}</p> : <>
              <label htmlFor="content">Document text</label>
              <textarea id="content" rows={7} required value={content} onChange={(e) => setContent(e.target.value)} maxLength={1048576} />
            </>}
            <button type="submit" disabled={media === 'application/pdf' && !pdf}>Index document</button>
          </form>
        </section>
        <section aria-labelledby="documents-title">
          <div className="section-title"><h2 id="documents-title">Your documents</h2>
            <button onClick={() => { clearEvidence(); setPendingDelete(null); void run(() => loadDocuments()); }}>Refresh documents</button></div>
          {!documents && <p>{busy ? 'Loading documents…' : 'Documents unavailable. Retry to load them.'}</p>}
          {documents && <>
            {documents.items.length === 0 && <p>No documents on this page. Index your first document to begin.</p>}
            <ul className="document-list">{documents.items.map((document) => <li key={document.id}>
              <h3>{document.source_key}</h3>
              <p className="subtle">{document.status} · version {document.version} · {document.chunk_count} passages</p>
              <div className="actions"><button onClick={() => inspectDocument(document)}>View passages</button>
                <button onClick={() => { setKey(document.source_key); setMedia(document.media_type); setContent(''); setPdf(null); setNotice('Replacement key selected. Provide new content or choose a file, then choose Index document.'); }}>Replace</button>
                <button className="danger" onClick={() => setPendingDelete(document)}>Delete</button></div>
              {capabilities?.retrieval_modes.includes('vector') && <button onClick={() => {
                clearEvidence();
                void run(async () => {
                  const indexed = await client.indexVectors(document.id);
                  setNotice(`${document.source_key}: ${indexed.chunk_count} passages indexed for semantic search with ${indexed.embedding_model}. Reindex after document changes.`);
                });
              }}>Index for semantic search</button>}
            </li>)}</ul>
            <Pager page={documents} busy={busy} label="Document pages" onPage={(offset) => void run(() => loadDocuments(offset))} />
          </>}
          {pendingDelete && <div className="confirmation" role="group" aria-label="Confirm document deletion">
            <p>Delete <strong>{pendingDelete.source_key}</strong> and all its indexed passages? This cannot be undone.</p>
            <div className="actions"><button className="danger" onClick={() => remove(pendingDelete)}>Confirm delete</button>
              <button onClick={() => setPendingDelete(null)}>Cancel deletion</button></div>
          </div>}
        </section>
      </div>
      <section aria-labelledby="search-title">
        <h2 id="search-title">Find evidence</h2>
        <p>Retrieve evidence from your documents. Finding a passage does not prove it answers the question.</p>
        <form onSubmit={(e) => { e.preventDefault(); setResult(null); setAnswer(null); setCitation(null); void run(async () => {
          if (mode === 'answer' && capabilities?.generation_enabled) setAnswer(await client.answer(question, retrievalMode));
          else setResult(await client.search(question, retrievalMode));
        }); }}>
          {capabilities && capabilities.retrieval_modes.length > 1 && <>
            <label htmlFor="retrieval-mode">Retrieval method</label>
            <select id="retrieval-mode" value={retrievalMode} onChange={(e) => {
              setRetrievalMode(e.target.value as RetrievalMode); setResult(null); setAnswer(null);
            }}>
              <option value="lexical">Lexical · matching words</option>
              <option value="vector">Vector · semantic similarity</option>
              <option value="hybrid">Hybrid · lexical and vector ranks</option>
            </select>
            <p className="subtle">Index documents for semantic search first. Updated documents need a new semantic index. Vector indexing currently supports 128 passages per document.</p>
          </>}
          <label htmlFor="question-mode">Response mode</label>
          <select id="question-mode" value={mode} onChange={(e) => { setMode(e.target.value as 'excerpts' | 'answer'); setResult(null); setAnswer(null); }}>
            <option value="excerpts">Retrieved source excerpts</option>
            {capabilities?.generation_enabled && <option value="answer">Grounded answer · local model</option>}
          </select>
          <p className="subtle">{capabilities?.generation_enabled
            ? 'Grounded answers use a local model to select verbatim claims with citations. Allow several minutes when local models need to load.'
            : 'Local model answers are not enabled or their availability has not been checked. Source search remains available.'}</p>
          <label htmlFor="question">Question or search terms</label>
          <div className="search-row"><input id="question" required maxLength={512} value={question} onChange={(e) => setQuestion(e.target.value)} />
            <button type="submit">{mode === 'answer' ? 'Ask local model' : 'Find passages'}</button></div>
        </form>
        <button onClick={() => void run(async () => { const state = await client.capabilities(); setCapabilities(state); if (!state.generation_enabled) setMode('excerpts'); })}>Check answer availability</button>
        {answer && <GroundedAnswer result={answer} inspect={inspect} />}
        {result && <div>
          <h3>{result.status === 'insufficient_evidence' ? 'Insufficient evidence' : 'Retrieved source excerpts'}</h3>
          {result.status === 'insufficient_evidence' && <p>No matching passages were found. Try different wording or index a relevant source. No answer was generated.</p>}
          {result.truncated && <p className="warning">{result.mode === 'hybrid' ? 'The lexical stage considered only the first 200 matching passages.' : `Search considered only the first ${result.candidate_limit} matching passages.`} Results may be incomplete.</p>}
          {result.mode !== 'lexical_excerpts' && <p className="subtle">
            {result.indexed_chunks} passages have matching embeddings; {result.unindexed_chunks} do not.
            {result.unindexed_chunks > 0 && ' Semantic results are incomplete until these passages are indexed.'}
          </p>}
          <p className="subtle">Retrieval: {result.duration_ms.toFixed(1)} ms · {result.retrieval_version}</p>
          {result.passages.map((passage) => <Excerpt key={passage.id} passage={passage} onInspect={inspect} />)}
        </div>}
      </section>
      {selected && <section aria-labelledby="passages-title">
        <h2 id="passages-title">Passages in {selected.source_key}</h2>
        {chunks ? <>{chunks.items.map((passage) => <Excerpt key={passage.id} passage={passage} onInspect={inspect} />)}
          <Pager page={chunks} busy={busy} label="Passage pages" onPage={(offset) => inspectDocument(selected, offset)} /></> : <p>Passages not loaded yet.</p>}
      </section>}
      {citation && <section className="source" aria-labelledby="source-title">
        <h2 id="source-title" tabIndex={-1} ref={sourceHeading}>Source inspection</h2>
        <p>This exact passage was retrieved again from the API under your access scope.</p>
        <Excerpt passage={citation} />
        <p className="subtle">Source ID: {citation.document_id}<br />Citation ID: {citation.id}</p>
        <button onClick={() => { setCitation(null); sourceTrigger.current?.focus(); }}>Close source inspection</button>
      </section>}
    </fieldset>
    <EvaluationReport />
  </>;
}
