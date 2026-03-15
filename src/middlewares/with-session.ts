import type { MiddlewareHandler } from 'hono'
import { createAuth } from '@/lib/auth'
import { AppBindings } from '@/lib/types';

const withSession: MiddlewareHandler<AppBindings> = async (c, next) => {
  const auth = createAuth(c.env);
  const session = await auth.api.getSession({ headers: c.req.raw.headers });

  if (!session) {
    c.set('user', null);
    c.set('session', null);
    return next();
  }

  c.set('user', {
    ...session.user,
    image: session.user.image ?? null,
  });

  c.set('session', {
    ...session.session,
    ipAddress: session.session.ipAddress ?? null,
    userAgent: session.session.userAgent ?? null,
  });

  return next();
};

export default withSession;
