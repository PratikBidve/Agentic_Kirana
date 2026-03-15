import type { Environment } from '@/env';
import type { user, session } from '@/db/schema';

type User = typeof user.$inferSelect;
type Session = typeof session.$inferSelect;

// Normalize Drizzle's optional (undefined) column types to null for Hono Variables
type Normalize<T> = {
  [K in keyof T]: undefined extends T[K] ? Exclude<T[K], undefined> | null : T[K];
};

export interface AppBindings {
  Bindings: Environment;
  Variables: {
    user: Normalize<User> | null;
    session: Normalize<Session> | null;
  };
}
