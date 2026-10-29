// Default: disposable browser_smoke_server and Vite. --container uses the
// local provisioned token privately; only document-list reads, never mutations.
const { chromium } = require('playwright');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs/promises');
const assert = require('node:assert/strict');

async function main() {
  const python = path.resolve('.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  // Actual evaluation serialization over a synthetic temporary API corpus.
  const reportIndex = process.argv.indexOf('--report');
  const fixture = reportIndex >= 0 ? JSON.parse(await fs.readFile(process.argv[reportIndex + 1], 'utf8'))
    : JSON.parse(execFileSync(python, ['frontend/scripts/provider_contract.py'], {
    encoding: 'utf8', timeout: 30000, stdio: ['ignore', 'pipe', 'pipe'],
  })).evaluation;
  assert.equal(fixture.official, false);
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const container = process.argv.includes('--container');
  const token = container ? (await fs.readFile('.local/local.token', 'utf8')).trim()
    : 'atlas-browser-smoke-synthetic-only';
  const output = path.resolve('.local/evaluation-browser-qa');
  await fs.mkdir(output, { recursive: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.name));
    await page.goto(container ? 'http://127.0.0.1:8080' : 'http://127.0.0.1:5173');
    await page.getByLabel('Access token').fill(token);
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await page.waitForFunction(() => !Array.from(document.querySelectorAll('button')).find(b => b.textContent === 'Refresh documents')?.disabled);
    const mutations = [];
    page.on('request', request => { if (request.method() !== 'GET') mutations.push(request.method()); });
    await page.getByLabel('Evaluation report JSON').setInputFiles({
      name: 'results.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(fixture)),
    });
    await page.getByRole('table', { name: 'Reported evaluation metrics' }).waitFor();
    await page.getByRole('row', { name: `Answer correctness Not measured 0 of ${fixture.summary.count}`, exact: true }).waitFor();
    const recorded = fixture.cases.filter(item => !item.failed && item.truncated !== undefined);
    await page.getByText(`Retrieval truncation: ${recorded.filter(item => item.truncated).length} of ${recorded.length} recorded cases.`, { exact: true }).waitFor();
    await page.getByText('Development report', { exact: true }).waitFor();
    await page.getByText('Recorded configuration and hashes', { exact: true }).click();
    // Inject via the automation context, preserving the application's CSP.
    await page.evaluate(await fs.readFile('frontend/node_modules/axe-core/axe.min.js', 'utf8'));
    const viewports = [];
    for (const width of [375, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      const violations = await page.evaluate(async () => (await window.axe.run(document, {
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] },
      })).violations.map(v => v.id));
      assert.deepEqual(violations, []);
      await page.getByRole('region', { name: 'Evaluation results' }).screenshot({
        path: path.join(output, `report-${width}.png`),
      });
      viewports.push({ width, overflow: false, axe_violations: violations });
    }
    await page.getByRole('button', { name: 'Disconnect' }).click();
    assert.equal(await page.getByRole('table').count(), 0);
    await page.getByLabel('Access token').fill(token);
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await page.getByText('No evaluation report loaded.', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
    assert.deepEqual(mutations, []);
    assert.deepEqual(errors, []);
    const report = { scope: reportIndex >= 0 ? 'saved development experiment report in Edge' : 'real Python-generated synthetic evaluation report in Edge', container,
      checks: ['local file loading', 'null ratings preserved', 'declared development status',
        'no report upload', 'disconnect/reconnect clears report', 'no browser persistence'],
      viewports, page_errors: errors, limitations: ['Not benchmark quality evidence', 'No screen reader or full WCAG certification'] };
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
