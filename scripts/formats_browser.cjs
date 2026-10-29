// Run only against the disposable synthetic format server on loopback port 8003.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

async function main() {
  const output = path.resolve('.local/formats-browser');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.name));
    page.on('response', response => { if (response.status() >= 400) errors.push(response.status()); });
    await page.goto('http://127.0.0.1:8003');
    await page.getByLabel('Access token').fill('atlas-format-browser-fixture');
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await page.getByText('No documents on this page.', { exact: false }).waitFor();
    const cases = [
      { name: 'synthetic.pdf', mimeType: 'application/pdf', buffer: await fs.readFile('.local/formats-fixture.pdf'), location: 'Page 1' },
      { name: 'synthetic.html', mimeType: 'text/html', buffer: Buffer.from('<h1>Token rotation</h1><p>Synthetic HTML policy.</p><script>window.atlasInjected=true</script>'), location: 'Heading: Token rotation' },
    ];
    const viewports = [];
    for (const fixture of cases) {
      await page.getByLabel('Choose a document file').setInputFiles({ name: fixture.name, mimeType: fixture.mimeType, buffer: fixture.buffer });
      await page.getByRole('button', { name: 'Index document', exact: true }).click();
      await page.getByRole('status').filter({ hasText: 'indexed. Version 1' }).waitFor();
      await page.getByRole('button', { name: 'View passages', exact: true }).click();
      await page.getByText(fixture.location, { exact: false }).waitFor();
      const inspect = page.getByRole('button', { name: 'Inspect source passage 1', exact: true });
      await inspect.focus();
      await page.keyboard.press('Enter');
      await page.waitForFunction(() => document.activeElement?.id === 'source-title');
      assert.equal(await page.evaluate(() => window.atlasInjected), undefined);
      for (const width of [375, 768, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        await page.screenshot({ path: path.join(output, `${fixture.name}-${width}.png`), fullPage: true });
        viewports.push({ format: fixture.mimeType, width, horizontal_overflow: false });
      }
      await page.getByRole('button', { name: 'Close source inspection' }).click();
      await page.getByRole('button', { name: 'Delete', exact: true }).click();
      await page.getByRole('button', { name: 'Confirm delete', exact: true }).click();
      await page.getByText('No documents on this page.', { exact: false }).waitFor();
    }
    await page.getByRole('button', { name: 'Disconnect', exact: true }).click();
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
    assert.deepEqual(errors, []);
    const report = { scope: 'synthetic SQLite loopback; real PDF/HTML parsers and built React UI',
      checks: ['file upload', 'source locations', 'keyboard citation focus', 'HTML script inert', 'delete', 'disconnect'],
      viewports, errors, visual_regression: 'inconclusive: no baseline', accessibility: 'keyboard focus only; not a full accessibility audit' };
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
