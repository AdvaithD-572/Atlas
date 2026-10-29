// Confirm the packaged frontend executes under its real CSP. No credentials used.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.name));
    page.on('console', message => { if (message.type() === 'error') errors.push({ text: message.text(), url: message.location().url }); });
    await page.goto('http://127.0.0.1:8080');
    await page.getByRole('heading', { name: 'Connect to your documents' }).waitFor();
    assert.equal(await page.getByLabel('Access token').isVisible(), true);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ scope: 'packaged frontend in Edge', react_rendered: true, errors }));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
