import type { Environment } from '@/env';
import type { user, session } from '@/db/schema';

type User = typeof user.$inferSelect;
type Session = typeof session.$inferSelect;

export interface AppBindings {
  Bindings: Environment;
  Variables: {
    user: User | null;
    session: Session | null;
  };
}
