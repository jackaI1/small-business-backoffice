import { z } from 'zod';
import { lines, statuses } from './contracts.js';

const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine(value => {
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}, 'Use a real calendar date in YYYY-MM-DD form');
const shape = { from: date.optional(), to: date.optional(), line: z.enum(lines).optional(), status: z.enum(statuses).optional() };
const orderedDates = (value: { from?: string; to?: string }) => !value.from || !value.to || value.from <= value.to;
const orderMessage = { message: 'from must be on or before to', path: ['to'] };
const integer = (max: number, fallback: string) => z.string().regex(/^[1-9]\d*$/).default(fallback)
  .transform(Number).pipe(z.number().int().min(1).max(max));
export const filterSchema = z.strictObject(shape).refine(orderedDates, orderMessage);
export const pageSchema = z.strictObject({ ...shape, page: integer(100000, '1'), pageSize: integer(100, '20') }).refine(orderedDates, orderMessage);
