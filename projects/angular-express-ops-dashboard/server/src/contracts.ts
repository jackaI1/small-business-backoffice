export const lines = ['alpha', 'beta', 'gamma'] as const;
export const statuses = ['complete', 'delayed'] as const;
export interface Filters { from?: string; to?: string; line?: typeof lines[number]; status?: typeof statuses[number] }
export interface Totals {
  runs: number; planned: number; produced: number; rejected: number;
  good: number; downtimeMinutes: number; rejectionRate: number | null;
}
export interface DailyTotals extends Totals { date: string }
export interface LineTotals extends Totals { line: typeof lines[number] }
export interface Run {
  id: number; date: string; line: typeof lines[number]; shift: 'day' | 'night';
  status: typeof statuses[number]; planned: number; produced: number; rejected: number; downtimeMinutes: number;
}
export interface Page<T> { data: T[]; page: number; pageSize: number; total: number; totalPages: number }
export interface Dashboard { summary: Totals; trends: DailyTotals[]; lines: LineTotals[]; runs: Page<Run> }
