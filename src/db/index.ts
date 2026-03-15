import { drizzle } from 'drizzle-orm/neon-http';
import { neon } from '@neondatabase/serverless';
import { Environment } from '@/env';
import * as schema from '@/db/schema';

let _db: ReturnType<typeof drizzle> | null = null;
let _dbUrl: string | null = null;

export function createDb(env: Environment) {
  // Singleton: reuse connection if DATABASE_URL hasn't changed
  if (_db && _dbUrl === env.DATABASE_URL) {
    return _db;
  }
  const sql = neon(env.DATABASE_URL);
  _db = drizzle(sql, { schema, casing: 'snake_case' });
  _dbUrl = env.DATABASE_URL;
  return _db;
}
