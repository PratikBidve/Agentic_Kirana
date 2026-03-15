import { createRouter } from '@/lib/create-app';
import { createDb } from '@/db';
import { store } from '@/db/schema';
import { eq, and } from 'drizzle-orm';
import { z } from 'zod';

const router = createRouter();

const CreateStoreSchema = z.object({
  name: z.string().min(1).max(200),
  phone: z.string().regex(/^[6-9]\d{9}$/, 'Enter valid 10-digit Indian mobile number').optional(),
  address: z.string().max(500).optional(),
  gstNumber: z
    .string()
    .regex(/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/, 'Invalid GST number')
    .optional(),
});

const UpdateStoreSchema = CreateStoreSchema.partial();

/**
 * POST /api/stores
 * Create a new kirana store linked to authenticated user
 */
router.post('/api/stores', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const body = await c.req.json();
  const parsed = CreateStoreSchema.safeParse(body);
  if (!parsed.success) return c.json({ error: 'Validation failed', details: parsed.error.flatten() }, 400);

  const db = createDb(c.env);
  const id = crypto.randomUUID();

  await db.insert(store).values({
    id,
    ownerId: user.id,
    ...parsed.data,
  });

  const [created] = await db.select().from(store).where(eq(store.id, id)).limit(1);
  return c.json(created, 201);
});

/**
 * GET /api/stores
 * List all stores owned by authenticated user
 */
router.get('/api/stores', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const db = createDb(c.env);
  const stores = await db.select().from(store).where(eq(store.ownerId, user.id));
  return c.json(stores);
});

/**
 * GET /api/stores/:storeId
 * Get single store — only owner can access
 */
router.get('/api/stores/:storeId', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const db = createDb(c.env);
  const [found] = await db
    .select()
    .from(store)
    .where(and(eq(store.id, c.req.param('storeId')), eq(store.ownerId, user.id)))
    .limit(1);

  if (!found) return c.json({ error: 'Store not found' }, 404);
  return c.json(found);
});

/**
 * PUT /api/stores/:storeId
 * Update store profile — only owner
 */
router.put('/api/stores/:storeId', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const body = await c.req.json();
  const parsed = UpdateStoreSchema.safeParse(body);
  if (!parsed.success) return c.json({ error: 'Validation failed', details: parsed.error.flatten() }, 400);

  const db = createDb(c.env);
  const [existing] = await db
    .select()
    .from(store)
    .where(and(eq(store.id, c.req.param('storeId')), eq(store.ownerId, user.id)))
    .limit(1);

  if (!existing) return c.json({ error: 'Store not found' }, 404);

  const [updated] = await db
    .update(store)
    .set({ ...parsed.data, updatedAt: new Date() })
    .where(eq(store.id, existing.id))
    .returning();

  return c.json(updated);
});

/**
 * DELETE /api/stores/:storeId
 * Soft-delete not implemented yet — hard delete for now
 */
router.delete('/api/stores/:storeId', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const db = createDb(c.env);
  const [existing] = await db
    .select()
    .from(store)
    .where(and(eq(store.id, c.req.param('storeId')), eq(store.ownerId, user.id)))
    .limit(1);

  if (!existing) return c.json({ error: 'Store not found' }, 404);

  await db.delete(store).where(eq(store.id, existing.id));
  return c.json({ message: 'Store deleted' });
});

export default router;
