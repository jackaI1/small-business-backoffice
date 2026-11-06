import { databasePath, openDatabase, seedDemo } from './database.js';
const db = openDatabase();
try {
  seedDemo(db);
  console.log(`Seeded 180 fictional production runs in ${databasePath()}`);
} finally {
  db.close();
}
