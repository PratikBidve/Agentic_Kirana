import { createRouter } from '@/lib/create-app';
import { createDb } from '@/db';
import { agentJob, product, store } from '@/db/schema';
import { getRedis, enqueueAgentJob } from '@/lib/redis';
import { eq, and } from 'drizzle-orm';
import { z } from 'zod';

const router = createRouter();

const MessageSchema = z.object({
  storeId: z.string().min(1),
  message: z.string().min(1).max(2000),
  waPhone: z.string().optional(), // E.164 phone — set when message arrives via WhatsApp
});

const ConfirmJobSchema = z.object({
  confirmed: z.literal(true),
});

// Helper: verify store ownership
async function verifyStoreOwner(
  db: ReturnType<typeof createDb>,
  storeId: string,
  userId: string
) {
  const [s] = await db
    .select()
    .from(store)
    .where(and(eq(store.id, storeId), eq(store.ownerId, userId)))
    .limit(1);
  return s ?? null;
}

/**
 * POST /api/agent/message
 * Enqueue an AI job. Returns jobId immediately (202 Accepted).
 * Supports optional waPhone for WhatsApp-originated messages.
 */
router.post('/api/agent/message', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const body = await c.req.json();
  const parsed = MessageSchema.safeParse(body);
  if (!parsed.success) {
    return c.json({ error: 'Invalid input', details: parsed.error.flatten() }, 400);
  }

  const { storeId, message, waPhone } = parsed.data;
  const db = createDb(c.env);
  const owned = await verifyStoreOwner(db, storeId, user.id);
  if (!owned) return c.json({ error: 'Store not found or unauthorized' }, 404);

  const redis = getRedis(c.env);
  const jobId = crypto.randomUUID();

  await db.insert(agentJob).values({
    id: jobId,
    storeId,
    input: message,
    status: 'pending',
  });

  await enqueueAgentJob(redis, jobId, storeId, message, waPhone);

  return c.json({ jobId, status: 'pending' }, 202);
});

/**
 * GET /api/agent/status/:jobId
 * Poll job status. Returns output when done.
 */
router.get('/api/agent/status/:jobId', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const jobId = c.req.param('jobId');
  const db = createDb(c.env);

  const [job] = await db
    .select()
    .from(agentJob)
    .where(eq(agentJob.id, jobId))
    .limit(1);

  if (!job) return c.json({ error: 'Job not found' }, 404);

  // Security: only store owner can read job
  const owned = await verifyStoreOwner(db, job.storeId, user.id);
  if (!owned) return c.json({ error: 'Unauthorized' }, 403);

  return c.json({
    jobId: job.id,
    status: job.status,
    output: job.output ?? null,
    dbPayload: job.agentSteps ? JSON.parse(job.agentSteps) : null,
    error: job.errorMessage ?? null,
    createdAt: job.createdAt,
    updatedAt: job.updatedAt,
  });
});

/**
 * POST /api/agent/jobs/:jobId/confirm
 * Owner confirms a staged AI action (inventory update or khata entry).
 * Reads db_payload from agent_job.agent_steps and applies the mutation.
 */
router.post('/api/agent/jobs/:jobId/confirm', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const body = await c.req.json();
  const parsed = ConfirmJobSchema.safeParse(body);
  if (!parsed.success) return c.json({ error: 'Send { confirmed: true }' }, 400);

  const jobId = c.req.param('jobId');
  const db = createDb(c.env);

  const [job] = await db
    .select()
    .from(agentJob)
    .where(eq(agentJob.id, jobId))
    .limit(1);

  if (!job) return c.json({ error: 'Job not found' }, 404);
  if (job.status !== 'done') return c.json({ error: `Job is ${job.status}, not confirmable` }, 409);

  const owned = await verifyStoreOwner(db, job.storeId, user.id);
  if (!owned) return c.json({ error: 'Unauthorized' }, 403);

  if (!job.agentSteps) return c.json({ error: 'No staged payload to confirm' }, 400);

  let payload: { type: string; [key: string]: unknown };
  try {
    payload = JSON.parse(job.agentSteps);
  } catch {
    return c.json({ error: 'Corrupt job payload' }, 500);
  }

  if (payload.type === 'inventory_update') {
    // Apply the staged stock change
    const [updated] = await db
      .update(product)
      .set({
        currentStock: String(payload.new_stock),
        updatedAt: new Date(),
      })
      .where(and(eq(product.id, payload.product_id as string), eq(product.storeId, job.storeId)))
      .returning();

    if (!updated) return c.json({ error: 'Product not found during confirm' }, 404);

    // Mark job confirmed
    await db.update(agentJob).set({ status: 'confirmed' }).where(eq(agentJob.id, jobId));

    return c.json({
      message: `✅ Stock updated: ${payload.product_name} → ${payload.new_stock}`,
      product: updated,
    });
  }

  if (payload.type === 'khata_entry') {
    // The khata entry is already in DB (unconfirmed). Confirm it.
    const entryId = payload.entry_id as string;
    // Delegate to khata confirm endpoint logic
    return c.json({
      message: `✅ Khata entry staged. Confirm via PATCH /api/stores/${job.storeId}/khata/${entryId}/confirm`,
      entryId,
    });
  }

  return c.json({ error: `Unknown payload type: ${payload.type}` }, 400);
});

export default router;
