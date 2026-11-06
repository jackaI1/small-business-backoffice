import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

export const databasePath = () => process.env['DATABASE_PATH'] ?? fileURLToPath(new URL('../../data/operations.sqlite', import.meta.url));
export function openDatabase(path = databasePath()): DatabaseSync {
  if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true });
  const db = new DatabaseSync(path);
  migrate(db);
  return db;
}
export function migrate(db: DatabaseSync): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS runs (
      id INTEGER PRIMARY KEY,
      date TEXT NOT NULL CHECK(length(date) = 10),
      line TEXT NOT NULL CHECK(line IN ('alpha', 'beta', 'gamma')),
      shift TEXT NOT NULL CHECK(shift IN ('day', 'night')),
      status TEXT NOT NULL CHECK(status IN ('complete', 'delayed')),
      planned INTEGER NOT NULL CHECK(planned >= 0),
      produced INTEGER NOT NULL CHECK(produced >= 0),
      rejected INTEGER NOT NULL CHECK(rejected >= 0 AND rejected <= produced),
      downtime_minutes INTEGER NOT NULL CHECK(downtime_minutes BETWEEN 0 AND 720),
      source TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('manual', 'demo'))
    );
    CREATE INDEX IF NOT EXISTS runs_date_id ON runs(date DESC, id DESC);
    CREATE INDEX IF NOT EXISTS runs_line_status_date ON runs(line, status, date);
  `);
}
/** Replace only explicitly marked demo rows, atomically. No random or clock inputs. */
export function seedDemo(db: DatabaseSync): void {
  db.exec('BEGIN IMMEDIATE');
  try {
    db.exec("DELETE FROM runs WHERE source = 'demo'");
    const insert = db.prepare(`INSERT INTO runs
      (id, date, line, shift, status, planned, produced, rejected, downtime_minutes, source)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'demo')`);
    for (let day = 0; day < 30; day++) {
      for (const [lineIndex, line] of ['alpha', 'beta', 'gamma'].entries()) {
        for (let shift = 0; shift < 2; shift++) {
          const id = 1000 + day * 6 + lineIndex * 2 + shift;
          const delayed = (day + lineIndex * 3 + shift) % 7 === 0;
          const planned = 400 + lineIndex * 100;
          const produced = planned - (delayed ? 90 : 10) - (day * 7 + shift * 11) % 30;
          const rejected = 3 + (day + lineIndex * 5 + shift) % 18;
          insert.run(id, `2026-10-${String(day + 1).padStart(2, '0')}`, line,
            shift === 0 ? 'day' : 'night', delayed ? 'delayed' : 'complete',
            planned, produced, rejected, delayed ? 40 + day % 25 : day % 8);
        }
      }
    }
    db.exec('COMMIT');
  } catch (error) {
    db.exec('ROLLBACK');
    throw error;
  }
}
