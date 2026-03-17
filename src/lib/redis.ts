import { Redis } from 'ioredis';

type Env = { REDIS_URL: string };

let _redis: Redis | null = null;

export function getRedis(env: Env): Redis {
  if (!_redis) {
    _redis = new Redis(env.REDIS_URL);
  }
  return _redis;
}

/**
 * Enqueue an agent job onto Redis list (LPUSH — worker does BRPOP from right).
 * waPhone is optional — only set for WhatsApp-originated messages.
 */
export async function enqueueAgentJob(
  redis: Redis,
  jobId: string,
  storeId: string,
  input: string,
  waPhone?: string
): Promise<void> {
  const payload = JSON.stringify({ jobId, storeId, input, waPhone: waPhone ?? null });
  await redis.lpush('agent_jobs', payload);
}
