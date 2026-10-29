// Run against scripts.browser_smoke_server and the loopback Vite server only.
// Uses the installed Playwright package (NODE_PATH may point to bundled tools).
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

async function main() {
  const output = path.resolve('.local/browser-qa');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(10000);
  const errors = [];
  const failures = [];
  page.on('pageerror', error => errors.push(error.name));
  page.on('response', response => { if (response.status() >= 400) failures.push(response.status()); });
  const checks = [];
  try {
    await page.goto('http://127.0.0.1:5173');
    await page.getByLabel('Access token').fill('atlas-browser-smoke-synthetic-only');
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await page.getByText('No documents on this page.', { exact: false }).waitFor();
    checks.push('authenticated empty state');
    await page.getByLabel('Document key', { exact: true }).fill('browser-smoke');
    await page.locator('#content').fill('The Atlas test server retries failed requests three times.');
    await page.getByRole('button', { name: 'Index document', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'browser-smoke indexed. Version 1' }).waitFor();
    checks.push('real upload and indexed status');
    const semanticButton = page.getByRole('button', { name: 'Index for semantic search', exact: true });
    const semantic = await semanticButton.count() > 0;
    if (semantic) {
      await semanticButton.click();
      await page.getByRole('status').filter({ hasText: 'passages indexed for semantic search' }).waitFor({ timeout: 250000 });
      for (const method of ['vector', 'hybrid']) {
        await page.getByLabel('Retrieval method').selectOption(method);
        await page.getByLabel('Question or search terms').fill('retry requests');
        await page.getByRole('button', { name: 'Find passages', exact: true }).click();
        await page.getByRole('button', { name: 'Inspect source passage 1', exact: true }).waitFor({ timeout: 130000 });
      }
      await page.getByLabel('Retrieval method').selectOption('lexical');
      checks.push('real embedding index, vector search and hybrid fusion');
    }
    await page.getByLabel('Question or search terms').fill('retry requests');
    await page.getByRole('button', { name: 'Find passages', exact: true }).click();
    const source = page.getByRole('button', { name: 'Inspect source passage 1', exact: true });
    await source.waitFor();
    await source.focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.activeElement?.id === 'source-title');
    await page.getByRole('button', { name: 'Close source inspection' }).click();
    assert.equal(await source.evaluate(el => el === document.activeElement), true);
    checks.push('lexical search, keyboard source inspection and focus restoration');
    await page.getByLabel('Response mode').selectOption('answer');
    if (semantic) await page.getByLabel('Retrieval method').selectOption('hybrid');
    await page.getByLabel('Question or search terms').fill('How many times does the Atlas test server retry failed requests?');
    await page.getByRole('button', { name: 'Ask local model', exact: true }).click();
    await page.getByRole('heading', { name: 'Grounded answer', exact: true }).waitFor({ timeout: 130000 });
    await page.getByRole('button', { name: 'Source 1: browser-smoke · v1' }).click();
    await page.getByRole('heading', { name: 'Source inspection', exact: true }).waitFor();
    checks.push('real local-model answer and reauthorized citation');
    await page.getByRole('button', { name: 'Close source inspection' }).click();
    const viewports = [];
    await page.addScriptTag({ path: path.resolve('frontend/node_modules/axe-core/axe.min.js') });
    for (const width of [375, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      assert.equal(overflow, false, `Horizontal overflow at ${width}`);
      const result = await page.evaluate(async () => {
        const result = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] } });
        return result.violations.map(v => ({ id: v.id, impact: v.impact, count: v.nodes.length }));
      });
      assert.deepEqual(result, [], `axe violations at ${width}`);
      await page.screenshot({ path: path.join(output, `atlas-${width}.png`), fullPage: true });
      viewports.push({ width, horizontal_overflow: false, axe_violations: result });
    }
    if (semantic) await page.getByLabel('Retrieval method').selectOption('lexical');
    await page.getByLabel('Question or search terms').fill('zyxqvnonexistent');
    await page.getByRole('button', { name: 'Ask local model', exact: true }).click();
    await page.getByRole('heading', { name: 'Insufficient evidence', exact: true }).waitFor();
    checks.push('empty retrieval abstention');
    await page.getByRole('button', { name: 'Replace', exact: true }).click();
    await page.locator('#content').fill('Replacement version: the server allows five retries.');
    await page.getByRole('button', { name: 'Index document', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Version 2' }).waitFor();
    await page.getByRole('button', { name: 'Delete', exact: true }).click();
    await page.getByRole('button', { name: 'Confirm delete', exact: true }).click();
    await page.getByText('No documents on this page.', { exact: false }).waitFor();
    checks.push('replacement version and confirmed deletion');
    await page.getByRole('button', { name: 'Disconnect', exact: true }).click();
    await page.getByRole('heading', { name: 'Connect to your documents' }).waitFor();
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
    assert.deepEqual(errors, []);
    assert.deepEqual(failures, []);
    checks.push('disconnect and no persisted browser token');
    const report = { scope: 'real loopback browser/API/Ollama, synthetic temporary data only', checks, viewports,
      page_errors: errors, http_failures: failures, visual_regression: 'inconclusive: no prior baseline',
      limitations: ['Screen reader and full WCAG conformance not verified', 'No quality benchmark or load test'] };
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
