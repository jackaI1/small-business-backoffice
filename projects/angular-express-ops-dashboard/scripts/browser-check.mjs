import assert from 'node:assert/strict';
import { test } from 'node:test';
import { chromium } from 'playwright';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import { mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
// QA: initial totals, all filters, next/previous, reset, empty/invalid ranges,
// backend failure/retry, desktop/mobile fit, and explicit owned-resource cleanup.
test('real dashboard journey at desktop and mobile widths', { timeout: 60000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), 'ops-browser-'));
  const env = { ...process.env, DATABASE_PATH: join(dir, 'demo.sqlite'), PORT: '0' };
  let server, exited, browserServer, browser, context, page;
  try {
    const seed = spawnSync(process.execPath, ['node_modules/tsx/dist/cli.mjs', 'server/src/seed.ts'], { cwd: root, env, encoding: 'utf8', timeout: 10000 });
    assert.equal(seed.status, 0, seed.stderr);
    const serverStart = new Date().toISOString();
    server = spawn(process.execPath, ['server/dist/index.js'], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
    exited = once(server, 'exit');
    let diagnostics = '';
    server.stderr.on('data', chunk => { diagnostics = (diagnostics + chunk).slice(-2000); });
    const base = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error(`Startup timeout: ${diagnostics}`)), 10000);
      server.once('exit', code => { clearTimeout(timeout); reject(new Error(`Startup exited ${code}: ${diagnostics}`)); });
      server.stdout.on('data', chunk => {
        const match = String(chunk).match(/http:\/\/localhost:(\d+)/);
        if (match) { clearTimeout(timeout); resolve(`http://127.0.0.1:${match[1]}`); }
      });
    });
    console.log(`Owned browser-check server PID=${server.pid} start=${serverStart} address=${base}; cleanup=SIGTERM in finally`);
    const browserStart = new Date().toISOString();
    browserServer = await chromium.launchServer({ headless: true });
    console.log(`Owned Chromium PID=${browserServer.process().pid} start=${browserStart} control-port=${new URL(browserServer.wsEndpoint()).port}; cleanup=browserServer.close() in finally`);
    browser = await chromium.connect(browserServer.wsEndpoint());
    context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    page = await context.newPage();
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', error => { if (errors.length < 10) errors.push(error.message); });
    await page.goto(base);
    await page.getByRole('heading', { name: 'Production overview' }).waitFor();
    await page.getByText('81,342', { exact: true }).waitFor();
    assert.equal(await page.getByTestId('run-row').count(), 10);
    assert.ok(await page.getByText('Page 1 of 18', { exact: true }).isVisible());
    const first = await page.getByTestId('run-row').first().innerText();
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await page.getByText('Page 2 of 18', { exact: true }).waitFor();
    assert.notEqual(await page.getByTestId('run-row').first().innerText(), first);
    await page.getByRole('button', { name: 'Previous', exact: true }).click();
    await page.getByText('Page 1 of 18', { exact: true }).waitFor();
    assert.equal(await page.getByTestId('run-row').first().innerText(), first);
    await page.getByLabel('From', { exact: true }).fill('2026-10-01');
    await page.getByLabel('Through', { exact: true }).fill('2026-10-07');
    await page.getByLabel('Production line', { exact: true }).selectOption('alpha');
    await page.getByLabel('Run status', { exact: true }).selectOption('delayed');
    await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
    await page.getByText('Page 1 of 1', { exact: true }).waitFor();
    assert.equal(await page.getByTestId('run-row').count(), 2);
    for (const row of await page.getByTestId('run-row').all()) {
      const text = await row.innerText(); assert.match(text, /Line A/); assert.match(text, /Delayed/);
    }
    await page.getByRole('button', { name: 'Reset', exact: true }).click();
    await page.getByText('Page 1 of 18', { exact: true }).waitFor();
    assert.equal(await page.getByLabel('From', { exact: true }).inputValue(), '');
    await page.getByLabel('From', { exact: true }).fill('2030-01-01');
    await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
    await page.getByRole('heading', { name: 'No runs match these filters' }).waitFor();
    assert.ok(await page.getByRole('button', { name: 'Next', exact: true }).isDisabled());
    await page.getByLabel('Through', { exact: true }).fill('2026-10-01');
    await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
    await page.getByRole('alert').waitFor();
    assert.match(await page.getByRole('alert').innerText(), /Check the filters/);
    await page.getByRole('button', { name: 'Reset', exact: true }).click();
    await page.getByText('Page 1 of 18', { exact: true }).waitFor();
    await page.route('**/api/**', route => route.fulfill({ status: 500, json: { error: { code: 'INTERNAL_ERROR' } } }));
    await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
    await page.getByRole('alert').waitFor();
    assert.match(await page.getByRole('alert').innerText(), /server/);
    await page.unroute('**/api/**');
    await page.getByRole('button', { name: 'Try again', exact: true }).click();
    await page.getByText('Page 1 of 18', { exact: true }).waitFor();
    for (const [width, height, filename] of [[1440, 1100, 'dashboard.png'], [390, 844, 'dashboard-mobile.png']]) {
      await page.setViewportSize({ width, height });
      await page.locator('.daily-scroll').evaluate(element => { element.scrollTop = 0; });
      assert.equal(await page.getByTestId('daily-totals').locator('tbody tr').count(), 30);
      await page.getByTestId('daily-totals').scrollIntoViewIfNeeded();
      await page.evaluate(() => window.scrollTo(0, 0));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `page overflow at ${width}px`);
      if (process.env['SCREENSHOT_DIR']) {
        mkdirSync(process.env['SCREENSHOT_DIR'], { recursive: true });
        await page.screenshot({ path: join(process.env['SCREENSHOT_DIR'], filename), fullPage: true });
      }
    }
    assert.deepEqual(errors, []);
  } finally {
    const cleanupErrors = [];
    const attempt = async action => { try { await action(); } catch (error) { cleanupErrors.push(error); } };
    // Every stage is attempted even if an earlier browser operation fails.
    if (page) await attempt(() => page.close());
    if (context) await attempt(async () => { await context.close(); assert.equal(context.pages().length, 0); });
    if (browser) await attempt(() => browser.close());
    if (browserServer) {
      const browserProcess = browserServer.process();
      await attempt(async () => {
        try { await browserServer.close(); }
        finally {
          if (browserProcess.exitCode === null && browserProcess.signalCode === null) {
            const stopped = once(browserProcess, 'exit');
            browserProcess.kill('SIGTERM');
            const force = setTimeout(() => browserProcess.kill('SIGKILL'), 5000);
            try { await stopped; } finally { clearTimeout(force); }
          }
        }
      });
      await attempt(() => {
        assert.throws(() => process.kill(browserProcess.pid, 0), { code: 'ESRCH' });
        console.log(`Verified owned Chromium PID=${browserProcess.pid} exited; owned pages=0`);
      });
    }
    await attempt(async () => {
      if (server && server.exitCode === null && server.signalCode === null) {
        server.kill('SIGTERM');
        const force = setTimeout(() => server.kill('SIGKILL'), 10000);
        try { await exited; } finally { clearTimeout(force); }
      }
      if (server) { assert.throws(() => process.kill(server.pid, 0), { code: 'ESRCH' }); console.log(`Verified owned browser-check server PID=${server.pid} exited`); }
    });
    await attempt(() => rmSync(dir, { recursive: true, force: true }));
    // eslint-disable-next-line no-unsafe-finally -- Cleanup failures must fail the browser check.
    if (cleanupErrors.length) throw new AggregateError(cleanupErrors, 'Fixture cleanup failed');
  }
});
