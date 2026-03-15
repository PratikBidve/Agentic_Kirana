import { Hono } from 'hono';
import { requestId } from 'hono/request-id';
import withSession from '@/middlewares/with-session';
import notFound from '@/middlewares/not-found';
import onError from '@/middlewares/on-error';
import authCors from '@/middlewares/auth-cors';
import { parseEnv } from '@/env';
import { AppBindings } from '@/lib/types';

export function createRouter() {
  return new Hono<AppBindings>({
    strict: false,
  });
}

export default function createApp() {
  const app = createRouter();

  // Inject validated env into every request context
  app.use((c, next) => {
    c.env = parseEnv(Object.assign(c.env || {}, process.env));
    return next();
  });

  // CORS only for auth routes
  app.use('/api/auth/*', authCors);

  // Session middleware ONLY on protected routes — not on public/health endpoints
  // This prevents a DB hit on every unauthenticated request
  app.use('/api/protected/*', withSession);

  app.use(requestId());
  app.onError(onError);
  app.notFound(notFound);

  return app;
}
