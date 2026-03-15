import { betterAuth } from 'better-auth';
import { drizzleAdapter } from 'better-auth/adapters/drizzle';
import { openAPI } from 'better-auth/plugins';
import { createDb } from '@/db';
import { Environment } from '@/env';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _auth: any = null;
let _authSecret: string | null = null;

// Singleton: betterAuth is expensive to instantiate, reuse per worker lifecycle
export function createAuth(env: Environment) {
  if (_auth && _authSecret === env.BETTER_AUTH_SECRET) {
    return _auth;
  }
  const db = createDb(env);
  _auth = betterAuth({
    secret: env.BETTER_AUTH_SECRET,
    baseURL: env.BETTER_AUTH_URL,
    socialProviders: {
      google: {
        clientId: env.GOOGLE_CLIENT_ID,
        clientSecret: env.GOOGLE_CLIENT_SECRET,
      },
    },
    database: drizzleAdapter(db, {
      provider: 'pg',
    }),
    plugins: [openAPI()],
  });
  _authSecret = env.BETTER_AUTH_SECRET;
  return _auth;
}
