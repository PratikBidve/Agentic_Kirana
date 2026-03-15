import type { MiddlewareHandler } from 'hono';
import type { AppBindings } from '@/lib/types';
import { getRedis } from '@/lib/redis';

/**
 * Redis-backed sliding window rate limiter
 * @param limit   max requests
 * @param windowSec  window in seconds
 */
export function rateLimit(
  limit = 60,
  windowSec = 60
): MiddlewareHandler<AppBindings> {
  return async (c, next) => {
    const redis = getRedis(c.env);
    // Key by IP; in Cloudflare Workers use CF-Connecting-IP header
    const ip =
      c.req.header('CF-Connecting-IP') ??
      c.req.header('X-Forwarded-For') ??
      'unknown';
    const key = `rl:${ip}:${Math.floor(Date.now() / (windowSec * 1000))}`;

    const current = await redis.incr(key);
    if (current === 1) await redis.expire(key, windowSec);

    c.header('X-RateLimit-Limit', String(limit));
    c.header('X-RateLimit-Remaining', String(Math.max(0, limit - current)));

    if (current > limit) {
      return c.json({ error: 'Too many requests. Slow down.' }, 429);
    }
    return next();
  };
}
