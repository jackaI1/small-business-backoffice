import type { DatabaseSync, SQLInputValue } from 'node:sqlite';
import type { DailyTotals, Filters, LineTotals, Page, Run, Totals } from './contracts.js';

function where(filters: Filters): { clause: string; params: SQLInputValue[] } {
  const parts: string[] = [];
  const params: SQLInputValue[] = [];
  for (const [key, operator, value] of [
    ['date', '>=', filters.from], ['date', '<=', filters.to],
    ['line', '=', filters.line], ['status', '=', filters.status],
  ] as const) {
    if (value !== undefined) { parts.push(`${key} ${operator} ?`); params.push(value); }
  }
  return { clause: parts.length ? `WHERE ${parts.join(' AND ')}` : '', params };
}
const totals = `COUNT(*) AS runs, COALESCE(SUM(planned), 0) AS planned,
  COALESCE(SUM(produced), 0) AS produced, COALESCE(SUM(rejected), 0) AS rejected,
  COALESCE(SUM(produced - rejected), 0) AS good,
  COALESCE(SUM(downtime_minutes), 0) AS downtimeMinutes,
  ROUND(100.0 * SUM(rejected) / NULLIF(SUM(produced), 0), 2) AS rejectionRate`;
export function summary(db: DatabaseSync, filters: Filters): Totals {
  const { clause, params } = where(filters);
  return db.prepare(`SELECT ${totals} FROM runs ${clause}`).get(...params) as unknown as Totals;
}
export function trends(db: DatabaseSync, filters: Filters): DailyTotals[] {
  const { clause, params } = where(filters);
  return db.prepare(`SELECT date, ${totals} FROM runs ${clause} GROUP BY date ORDER BY date`).all(...params) as unknown as DailyTotals[];
}
export function byLine(db: DatabaseSync, filters: Filters): LineTotals[] {
  const { clause, params } = where(filters);
  return db.prepare(`SELECT line, ${totals} FROM runs ${clause} GROUP BY line ORDER BY line`).all(...params) as unknown as LineTotals[];
}
export function runs(db: DatabaseSync, filters: Filters & { page: number; pageSize: number }): Page<Run> {
  const { clause, params } = where(filters);
  const total = Number(db.prepare(`SELECT COUNT(*) AS n FROM runs ${clause}`).get(...params)!['n']);
  const data = db.prepare(`SELECT id, date, line, shift, status, planned, produced, rejected,
    downtime_minutes AS downtimeMinutes FROM runs ${clause} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?`)
    .all(...params, filters.pageSize, (filters.page - 1) * filters.pageSize) as unknown as Run[];
  return { data, page: filters.page, pageSize: filters.pageSize, total, totalPages: Math.ceil(total / filters.pageSize) };
}
