import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import request from 'supertest';
import { DatabaseSync } from 'node:sqlite';
import { createApp } from '../src/app.js';
import { migrate, seedDemo } from '../src/database.js';

let db: DatabaseSync;
beforeEach(() => {
  db = new DatabaseSync(':memory:');
  migrate(db);
  const insert = db.prepare('INSERT INTO runs (id, date, line, shift, status, planned, produced, rejected, downtime_minutes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)');
  for (const row of [
    [1, '2026-10-01', 'alpha', 'day', 'complete', 100, 100, 5, 10],
    [2, '2026-10-01', 'beta', 'night', 'delayed', 200, 100, 15, 30],
    [3, '2026-10-02', 'alpha', 'night', 'complete', 300, 300, 0, 0],
    [4, '2026-10-03', 'gamma', 'day', 'delayed', 50, 0, 0, 60],
  ]) insert.run(...row);
});
afterEach(() => { if (db.isOpen) db.close(); });

describe('SQLite-backed Express API', () => {
  it('aggregates all rows using a weighted rejection rate', async () => {
    const res = await request(createApp(db)).get('/api/summary').expect(200);
    expect(res.body).toEqual({ runs: 4, planned: 650, produced: 500, rejected: 20, good: 480, downtimeMinutes: 100, rejectionRate: 4 });
  });
  it('applies inclusive dates, line and status together', async () => {
    const res = await request(createApp(db)).get('/api/summary?from=2026-10-01&to=2026-10-01&line=alpha&status=complete').expect(200);
    expect(res.body).toEqual({ runs: 1, planned: 100, produced: 100, rejected: 5, good: 95, downtimeMinutes: 10, rejectionRate: 5 });
  });
  it('groups daily totals chronologically and applies filters', async () => {
    const res = await request(createApp(db)).get('/api/trends?line=alpha').expect(200);
    expect(res.body.data).toEqual([
      { date: '2026-10-01', runs: 1, planned: 100, produced: 100, rejected: 5, good: 95, downtimeMinutes: 10, rejectionRate: 5 },
      { date: '2026-10-02', runs: 1, planned: 300, produced: 300, rejected: 0, good: 300, downtimeMinutes: 0, rejectionRate: 0 },
    ]);
  });
  it('compares line totals, including a line with no output', async () => {
    const res = await request(createApp(db)).get('/api/lines?status=delayed').expect(200);
    expect(res.body.data).toEqual([
      { line: 'beta', runs: 1, planned: 200, produced: 100, rejected: 15, good: 85, downtimeMinutes: 30, rejectionRate: 15 },
      { line: 'gamma', runs: 1, planned: 50, produced: 0, rejected: 0, good: 0, downtimeMinutes: 60, rejectionRate: null },
    ]);
  });
  it('uses stable date-descending, id-descending pages without overlap', async () => {
    const app = createApp(db);
    const first = await request(app).get('/api/runs?pageSize=2').expect(200);
    const second = await request(app).get('/api/runs?pageSize=2&page=2').expect(200);
    expect(first.body).toMatchObject({ page: 1, pageSize: 2, total: 4, totalPages: 2 });
    expect(first.body.data.map((r: {id: number}) => r.id)).toEqual([4, 3]);
    expect(second.body.data.map((r: {id: number}) => r.id)).toEqual([2, 1]);
    expect(second.body.data[1]).toEqual({ id: 1, date: '2026-10-01', line: 'alpha', shift: 'day', status: 'complete', planned: 100, produced: 100, rejected: 5, downtimeMinutes: 10 });
  });
  it('paginates filtered rows without changing aggregate totals', async () => {
    const app = createApp(db);
    const page = await request(app).get('/api/runs?line=alpha&pageSize=1&page=2').expect(200);
    expect(page.body).toMatchObject({ total: 2, totalPages: 2 });
    expect(page.body.data[0].id).toBe(1);
    const summary = await request(app).get('/api/summary?line=alpha').expect(200);
    expect(summary.body.produced).toBe(400);
  });
  it('returns useful empty results and permits pages beyond the last', async () => {
    const app = createApp(db);
    const summary = await request(app).get('/api/summary?from=2030-01-01').expect(200);
    expect(summary.body).toEqual({ runs: 0, planned: 0, produced: 0, rejected: 0, good: 0, downtimeMinutes: 0, rejectionRate: null });
    for (const route of ['trends', 'lines', 'runs']) {
      const res = await request(app).get(`/api/${route}?from=2030-01-01`).expect(200);
      expect(res.body.data).toEqual([]);
    }
    const page = await request(app).get('/api/runs?page=99').expect(200);
    expect(page.body.data).toEqual([]);
    expect(page.body.total).toBe(4);
  });
  it.each([
    'from=2026-02-30', 'to=2026-13-01', 'from=26-01-01', 'from=2026-10-03&to=2026-10-01',
    'line=unknown', 'status=unknown', 'line=alpha&line=beta', 'line[]=alpha', 'from=', 'unexpected=1',
    'page=0', 'page=-1', 'page=1.5', 'page=1e2', 'page=100001', 'pageSize=101', 'pageSize=0',
    'pageSize=2&pageSize=3', 'page=', 'line=alpha%27%20OR%201%3D1--',
  ])('rejects malformed run query %s with structured 400 errors', async query => {
    const res = await request(createApp(db)).get(`/api/runs?${query}`).expect(400);
    expect(res.body.error.code).toBe('INVALID_QUERY');
    expect(res.body.error.details.length).toBeGreaterThan(0);
  });
  it.each(['summary', 'trends', 'lines'])('enforces filter validation on %s, including pagination-only params', async route => {
    await request(createApp(db)).get(`/api/${route}?from=2026-02-30`).expect(400);
    await request(createApp(db)).get(`/api/${route}?page=1`).expect(400);
  });
  it('returns JSON for unknown API routes', async () => {
    const res = await request(createApp(db)).get('/api/missing').expect(404);
    expect(res.body.error.code).toBe('NOT_FOUND');
  });
  it('hides database errors behind generic error middleware', async () => {
    const app = createApp(db);
    db.close();
    const res = await request(app).get('/api/summary').expect(500);
    expect(res.body).toEqual({ error: { code: 'INTERNAL_ERROR', message: 'The request could not be completed. Try again.' } });
  });
  it('rate limits API traffic and ignores spoofed forwarding headers', async () => {
    const app = createApp(db, { rateLimitMax: 2 });
    await request(app).get('/api/summary').expect(200);
    await request(app).get('/api/runs').expect(200);
    const res = await request(app).get('/api/lines').set('X-Forwarded-For', '203.0.113.1').expect(429);
    expect(res.body.error.code).toBe('RATE_LIMITED');
    expect(Number(res.headers['retry-after'])).toBeGreaterThan(0);
  });
  it('reproduces 180 fictional runs when seeded twice and preserves unrelated rows', () => {
    seedDemo(db);
    const first = db.prepare('SELECT * FROM runs WHERE id >= 1000 ORDER BY id').all();
    seedDemo(db);
    expect(db.prepare('SELECT * FROM runs WHERE id >= 1000 ORDER BY id').all()).toEqual(first);
    expect(first).toHaveLength(180);
    expect(db.prepare('SELECT COUNT(*) AS n FROM runs WHERE id < 1000').get()).toEqual({ n: 4 });
  });
  it('enforces data constraints in the store', () => {
    expect(() => db.prepare("UPDATE runs SET rejected = produced + 1 WHERE id = 1").run()).toThrow();
  });
});
