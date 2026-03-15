import { Redis } from 'ioredis';
import { Environment } from '@/env';

let _redis: Redis | null = null;

// Singleton Redis client — reuse across requests in same worker lifecycle
export function getRedis(env: Environment): Redis {
  if (_redis) return _redis;
  _redis = new Redis(env.REDIS_URL, {
    maxRetriesPerRequest: 3,
    retryStrategy: (times) => Math.min(times * 100, 3000),
    lazyConnect: true,
  });
  _redis.on('error', (err) => console.error('[Redis] connection error:', err));
  return _redis;
}

/**
 * Push an agent job to the queue consumed by FastAPI/LangGraph worker
 */
export async function enqueueAgentJob(
  redis: Redis,
  jobId: string,
  storeId: string,
  input: string
): Promise<void> {
  await redis.lpush(
    'agent_jobs',
    JSON.stringify({ jobId, storeId, input, enqueuedAt: new Date().toISOString() })
  );
}
