import { fileURLToPath } from 'node:url';
import { createApp } from './app.js';
import { openDatabase } from './database.js';
import { createApp as createVenueApp } from '../app.mjs';
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';

const port = Number(process.env['PORT'] ?? 3000);
if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('PORT must be an integer from 0 to 65535');
const db = openDatabase();
const app = createApp(db, {
  extraRoutes: createVenueApp({ apiOnly: true }),
  venueDir: fileURLToPath(new URL('../../dist/venue/browser/', import.meta.url)),
  staticDir: fileURLToPath(new URL('../../web/dist/ops-dashboard/browser/', import.meta.url)),
  onError: error => console.error('API request failed:', error instanceof Error ? error.message : 'Unknown error'),
});
const server = app.listen(port, '127.0.0.1', () => {
  const address = server.address();
  if (address && typeof address !== 'string') {
    mkdirSync('.runtime', { recursive: true });
    writeFileSync(`.runtime/server-${address.port}.json`, JSON.stringify({ owner: 'operations dashboard', pid: process.pid, started: new Date().toISOString(), port: address.port, cleanup: `kill -TERM ${process.pid}` }));
    console.log(`Dashboard ready at http://localhost:${address.port}`);
  }
});
server.on('error', error => { db.close(); console.error(error.message); process.exitCode = 1; });
let stopping = false;
function shutdown() {
  if (stopping) return;
  stopping = true;
  const address = server.address();
  server.close(() => {
    db.close();
    if (address && typeof address !== 'string') rmSync(`.runtime/server-${address.port}.json`, { force: true });
  });
  const timeout = setTimeout(() => { server.closeAllConnections(); }, 5000);
  timeout.unref();
}
process.once('SIGINT', shutdown);
process.once('SIGTERM', shutdown);
