/** Real Chrome DOM regression: accessible names must survive into agent senses. */
import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const root = resolve(import.meta.dirname, '../..');
const candidates = [process.env.ANTICIPY_PLAYWRIGHT_MODULE,
  ...readdirSync(join(homedir(), '.npm/_npx')).map(n =>
    join(homedir(), '.npm/_npx', n, 'node_modules/playwright/index.mjs'))].filter(Boolean);
const modulePath = candidates.find(existsSync);
assert(modulePath, 'Install the Playwright CLI runtime first');
const { chromium } = await import(pathToFileURL(modulePath));
const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  const page = await browser.newPage();
  await page.setContent(`<style>label,input,select{display:block;margin:12px}</style>
    <label>Start time<input name="start" type="datetime-local" value="2026-09-10T10:00"></label>
    <label>End time<input name="end" type="datetime-local" value="2026-09-10T11:00"></label>
    <label for="title">Appointment title</label><input id="title" name="title" value="Supplier review">
    <span id="a">Billing</span><span id="b">reference</span><input name="reference" aria-labelledby="a b" value="R-26">
    <label>Display name<input name="display" aria-label="Preferred name" value="Casey"></label>
    <label>Office<select name="office"><option selected>Seattle</option><option>Vancouver</option></select></label>`);
  await page.addScriptTag({ content: readFileSync(join(root, 'extension/page_map.js'), 'utf8') });
  const mapped = await page.evaluate(() => window.__anticipyMapPage());
  const actual = Object.fromEntries(mapped.fields.map(f => [f.name, f.label]));
  const expected = { start: 'Start time', end: 'End time', title: 'Appointment title',
    reference: 'Billing reference', display: 'Preferred name', office: 'Office' };
  for (const [name, label] of Object.entries(expected)) assert.equal(actual[name], label, name);
  const evidence = { passed: true, browser: 'Real isolated Chrome', expected, actual };
  writeFileSync(join(root, 'work/audit/overnight-page-labels.json'), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify(evidence));
} finally { await browser.close(); }
