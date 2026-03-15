import { createRouter } from '@/lib/create-app';
import { createDb } from '@/db';
import { agentJob } from '@/db/schema';
import { getRedis, enqueueAgentJob } from '@/lib/redis';
import { eq } from 'drizzle-orm';
import { z } from 'zod';

const router = createRouter();

const MessageSchema = z.object({
  storeId: z.string().min(1),
  message: z.string().min(1).max(2000),
});

/**
 * POST /api/agent/message
 * Receives user/WhatsApp message, persists job, enqueues to Redis
 * Returns immediately with jobId — never waits for AI response
 */
router.post('/api/agent/message', async (c) => {
  const body = await c.req.json();
  const parsed = MessageSchema.safeParse(body);

  if (!parsed.success) {
    return c.json({ error: 'Invalid input', details: parsed.error.flatten() }, 400);
  }

  const { storeId, message } = parsed.data;
  const db = createDb(c.env);
  const redis = getRedis(c.env);
  const jobId = crypto.randomUUID();

  // 1. Persist job as pending in DB
  await db.insert(agentJob).values({
    id: jobId,
    storeId,
    input: message,
    status: 'pending',
  });

  // 2. Push to Redis queue — FastAPI/LangGraph worker picks this up
  await enqueueAgentJob(redis, jobId, storeId, message);

  return c.json({ jobId, status: 'pending' }, 202);
});

/**
 * GET /api/agent/status/:jobId
 * Poll job status — client polls until status is 'done' or 'failed'
 */
router.get('/api/agent/status/:jobId', async (c) => {
  const jobId = c.req.param('jobId');
  const db = createDb(c.env);

  const [job] = await db
    .select()
    .from(agentJob)
    .where(eq(agentJob.id, jobId))
    .limit(1);

  if (!job) {
    return c.json({ error: 'Job not found' }, 404);
  }

  return c.json({
    jobId: job.id,
    status: job.status,
    output: job.output ?? null,
    error: job.errorMessage ?? null,
    createdAt: job.createdAt,
    updatedAt: job.updatedAt,
  });
});

export default router;
