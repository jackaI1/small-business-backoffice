import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
test('clean seed and compiled Express + Angular HTTP journey', { timeout: 30000 }, async () => {
  const directory = mkdtempSync(join(tmpdir(), 'ops-smoke-'));
  const path = join(directory, 'demo.sqlite');
  const env = { ...process.env, DATABASE_PATH: path, PORT: '0' };
  let child;
  let exited;
  try {
    const snapshots = [];
    for (let pass = 0; pass < 2; pass++) {
      const seed = spawnSync(process.execPath, ['node_modules/tsx/dist/cli.mjs', 'server/src/seed.ts'], { cwd: root, env, encoding: 'utf8', timeout: 10000 });
      assert.equal(seed.status, 0, seed.stderr);
      const db = new DatabaseSync(path);
      try { snapshots.push(db.prepare('SELECT * FROM runs ORDER BY id').all()); }
      finally { db.close(); }
    }
    assert.equal(snapshots[0].length, 180);
    assert.deepEqual(snapshots[0], snapshots[1]);
    const serverStart = new Date().toISOString();
    child = spawn(process.execPath, ['server/dist/index.js'], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
    exited = once(child, 'exit');
    let diagnostics = '';
    child.stderr.on('data', chunk => { diagnostics = (diagnostics + chunk).slice(-2000); });
    const base = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error(`Startup timed out: ${diagnostics}`)), 10000);
      child.once('exit', code => { clearTimeout(timeout); reject(new Error(`Server exited ${code}: ${diagnostics}`)); });
      child.stdout.on('data', chunk => {
        const match = String(chunk).match(/http:\/\/localhost:(\d+)/);
        if (match) { clearTimeout(timeout); resolve(`http://127.0.0.1:${match[1]}`); }
      });
    });
    console.log(`Owned smoke server PID=${child.pid}, start=${serverStart}, address=${base}; cleanup=SIGTERM and await exit (finally)`);
    const get = async route => {
      const response = await fetch(`${base}${route}`);
      assert.equal(response.status, 200);
      return response.json();
    };
    assert.deepEqual(await get('/api/health'), { status: 'ok' });
    const summary = await get('/api/summary');
    assert.equal(summary.runs, 180);
    assert.equal(summary.planned, 90000);
    assert.equal(summary.produced, 83430);
    assert.equal(summary.rejected, 2088);
    assert.equal(summary.good, 81342);
    assert.equal(summary.rejectionRate, 2.5);
    const filtered = await get('/api/summary?line=alpha&from=2026-10-01&to=2026-10-01');
    assert.deepEqual(filtered, { runs: 2, planned: 800, produced: 689, rejected: 7, good: 682, downtimeMinutes: 40, rejectionRate: 1.02 });
    const page = await get('/api/runs?page=2&pageSize=10');
    assert.equal(page.totalPages, 18);
    assert.equal(page.data.length, 10);
    assert.equal(page.page, 2);
    const bad = await fetch(`${base}/api/runs?pageSize=101`);
    assert.equal(bad.status, 400);
    const missing = await fetch(`${base}/api/missing`);
    assert.equal(missing.status, 404);
    const htmlResponse = await fetch(base);
    assert.equal(htmlResponse.status, 200);
    const html = await htmlResponse.text();
    assert.match(html, /<app-root/);
    const script = html.match(/src="(main-[^"]+\.js)"/);
    assert.ok(script, 'compiled Angular entry script is linked');
    const bundle = await fetch(`${base}/${script[1]}`);
    assert.equal(bundle.status, 200);
    assert.match(bundle.headers.get('content-type'), /javascript/);
  } finally {
    if (child && child.exitCode === null && child.signalCode === null) {
      child.kill('SIGTERM');
      const force = setTimeout(() => child.kill('SIGKILL'), 10000);
      try { await exited; } finally { clearTimeout(force); }
    }
    if (child) {
      assert.throws(() => process.kill(child.pid, 0), { code: 'ESRCH' });
      console.log(`Verified owned smoke server PID=${child.pid} exited`);
    }
    rmSync(directory, { recursive: true, force: true });
  }
});
