import express, { type ErrorRequestHandler } from 'express';
import { rateLimit } from 'express-rate-limit';
import { ZodError } from 'zod';
import type { DatabaseSync } from 'node:sqlite';
import { filterSchema, pageSchema } from './validation.js';
import { byLine, runs, summary, trends } from './queries.js';

interface Options { rateLimitMax?: number; staticDir?: string; venueDir?: string; extraRoutes?: express.RequestHandler; onError?: (error: unknown) => void }
export function createApp(db: DatabaseSync, options: Options = {}) {
  const app = express();
  app.disable('x-powered-by');
  app.set('query parser', 'simple');
  // Direct local hosting only. Forwarding headers are deliberately not trusted.
  app.set('trust proxy', false);
  app.use('/api', rateLimit({
    windowMs: 60_000, limit: options.rateLimitMax ?? 300,
    standardHeaders: 'draft-8', legacyHeaders: false,
    // A spoofed header must neither change identity nor cause noisy validation logs.
    validate: { xForwardedForHeader: false },
    handler: (_req, res) => res.status(429).json({ error: {
      code: 'RATE_LIMITED', message: 'Too many requests. Wait one minute and try again.',
    } }),
  }));
  app.get('/api/health', (_req, res) => {
    db.prepare('SELECT 1').get();
    res.json({ status: 'ok' });
  });
  app.get('/api/summary', (req, res) => res.json(summary(db, filterSchema.parse(req.query))));
  app.get('/api/trends', (req, res) => res.json({ data: trends(db, filterSchema.parse(req.query)) }));
  app.get('/api/lines', (req, res) => res.json({ data: byLine(db, filterSchema.parse(req.query)) }));
  app.get('/api/runs', (req, res) => res.json(runs(db, pageSchema.parse(req.query))));
  if (options.extraRoutes) app.use(options.extraRoutes);
  if (options.venueDir) {
    app.use('/venue', express.static(options.venueDir));
    app.get('/venue/{*path}', (_req, res) => res.sendFile('index.html', { root: options.venueDir! }));
  }
  const notFound: express.RequestHandler = (_req, res) => { res.status(404).json({ error: { code: 'NOT_FOUND', message: 'Route not found.' } }); };
  app.use('/api', notFound);
  if (options.staticDir) app.use(express.static(options.staticDir));
  app.use(notFound);
  const errorHandler: ErrorRequestHandler = (error, _req, res, _next) => {
    if (error instanceof ZodError) {
      res.status(400).json({ error: { code: 'INVALID_QUERY', message: 'Check the query parameters.',
        details: error.issues.map(issue => ({ field: issue.path.join('.'), message: issue.message })),
      } });
      return;
    }
    options.onError?.(error);
    res.status(500).json({ error: { code: 'INTERNAL_ERROR', message: 'The request could not be completed. Try again.' } });
  };
  app.use(errorHandler);
  return app;
}
