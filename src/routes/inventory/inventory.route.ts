import { createRouter } from '@/lib/create-app';
import { createDb } from '@/db';
import { product, store } from '@/db/schema';
import { eq, and, lte, sql } from 'drizzle-orm';
import { z } from 'zod';

const router = createRouter();

const ProductSchema = z.object({
  name: z.string().min(1).max(200),
  nameAliases: z.string().max(500).optional(),
  unit: z.enum(['kg', 'piece', 'litre', 'dozen', 'pack', 'gram', 'ml']),
  currentStock: z.number().min(0),
  reorderLevel: z.number().min(0).optional(),
  sellingPrice: z.number().positive(),
  costPrice: z.number().positive().optional(),
  category: z.enum(['grocery', 'snacks', 'dairy', 'beverages', 'household', 'other']).optional(),
});

const UpdateStockSchema = z.object({
  currentStock: z.number().min(0),
  note: z.string().max(200).optional(),
});

// Helper: verify store ownership
async function verifyStoreOwner(db: ReturnType<typeof createDb>, storeId: string, userId: string) {
  const [s] = await db
    .select()
    .from(store)
    .where(and(eq(store.id, storeId), eq(store.ownerId, userId)))
    .limit(1);
  return s ?? null;
}

/**
 * POST /api/stores/:storeId/products
 * Add a new product to inventory
 */
router.post('/api/stores/:storeId/products', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const body = await c.req.json();
  const parsed = ProductSchema.safeParse(body);
  if (!parsed.success) return c.json({ error: 'Validation failed', details: parsed.error.flatten() }, 400);

  const db = createDb(c.env);
  const owned = await verifyStoreOwner(db, c.req.param('storeId'), user.id);
  if (!owned) return c.json({ error: 'Store not found' }, 404);

  const id = crypto.randomUUID();
  await db.insert(product).values({
    id,
    storeId: owned.id,
    ...parsed.data,
    currentStock: String(parsed.data.currentStock),
    reorderLevel: parsed.data.reorderLevel ? String(parsed.data.reorderLevel) : '0',
    sellingPrice: String(parsed.data.sellingPrice),
    costPrice: parsed.data.costPrice ? String(parsed.data.costPrice) : null,
  });

  const [created] = await db.select().from(product).where(eq(product.id, id)).limit(1);
  return c.json(created, 201);
});

/**
 * GET /api/stores/:storeId/products
 * List all active products in store
 * Query param: ?lowStock=true to filter items below reorder level
 */
router.get('/api/stores/:storeId/products', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const db = createDb(c.env);
  const owned = await verifyStoreOwner(db, c.req.param('storeId'), user.id);
  if (!owned) return c.json({ error: 'Store not found' }, 404);

  const lowStockOnly = c.req.query('lowStock') === 'true';

  const products = await db
    .select()
    .from(product)
    .where(
      lowStockOnly
        ? and(
            eq(product.storeId, owned.id),
            eq(product.isActive, true),
            lte(product.currentStock, sql`${product.reorderLevel}`)
          )
        : and(eq(product.storeId, owned.id), eq(product.isActive, true))
    );

  return c.json(products);
});

/**
 * GET /api/stores/:storeId/products/:productId
 * Get single product
 */
router.get('/api/stores/:storeId/products/:productId', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const db = createDb(c.env);
  const owned = await verifyStoreOwner(db, c.req.param('storeId'), user.id);
  if (!owned) return c.json({ error: 'Store not found' }, 404);

  const [found] = await db
    .select()
    .from(product)
    .where(and(eq(product.id, c.req.param('productId')), eq(product.storeId, owned.id)))
    .limit(1);

  if (!found) return c.json({ error: 'Product not found' }, 404);
  return c.json(found);
});

/**
 * PUT /api/stores/:storeId/products/:productId
 * Update product details
 */
router.put('/api/stores/:storeId/products/:productId', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const body = await c.req.json();
  const parsed = ProductSchema.partial().safeParse(body);
  if (!parsed.success) return c.json({ error: 'Validation failed', details: parsed.error.flatten() }, 400);

  const db = createDb(c.env);
  const owned = await verifyStoreOwner(db, c.req.param('storeId'), user.id);
  if (!owned) return c.json({ error: 'Store not found' }, 404);

  const updateData: Record<string, unknown> = { updatedAt: new Date() };
  if (parsed.data.name) updateData.name = parsed.data.name;
  if (parsed.data.nameAliases !== undefined) updateData.nameAliases = parsed.data.nameAliases;
  if (parsed.data.unit) updateData.unit = parsed.data.unit;
  if (parsed.data.currentStock !== undefined) updateData.currentStock = String(parsed.data.currentStock);
  if (parsed.data.reorderLevel !== undefined) updateData.reorderLevel = String(parsed.data.reorderLevel);
  if (parsed.data.sellingPrice !== undefined) updateData.sellingPrice = String(parsed.data.sellingPrice);
  if (parsed.data.costPrice !== undefined) updateData.costPrice = String(parsed.data.costPrice);
  if (parsed.data.category) updateData.category = parsed.data.category;

  const [updated] = await db
    .update(product)
    .set(updateData)
    .where(and(eq(product.id, c.req.param('productId')), eq(product.storeId, owned.id)))
    .returning();

  if (!updated) return c.json({ error: 'Product not found' }, 404);
  return c.json(updated);
});

/**
 * PATCH /api/stores/:storeId/products/:productId/stock
 * Quick stock adjustment — used by AI agent after confirmed restock
 */
router.patch('/api/stores/:storeId/products/:productId/stock', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const body = await c.req.json();
  const parsed = UpdateStockSchema.safeParse(body);
  if (!parsed.success) return c.json({ error: 'Validation failed', details: parsed.error.flatten() }, 400);

  const db = createDb(c.env);
  const owned = await verifyStoreOwner(db, c.req.param('storeId'), user.id);
  if (!owned) return c.json({ error: 'Store not found' }, 404);

  const [updated] = await db
    .update(product)
    .set({ currentStock: String(parsed.data.currentStock), updatedAt: new Date() })
    .where(and(eq(product.id, c.req.param('productId')), eq(product.storeId, owned.id)))
    .returning();

  if (!updated) return c.json({ error: 'Product not found' }, 404);
  return c.json(updated);
});

/**
 * DELETE /api/stores/:storeId/products/:productId
 * Soft delete — marks isActive = false
 */
router.delete('/api/stores/:storeId/products/:productId', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const db = createDb(c.env);
  const owned = await verifyStoreOwner(db, c.req.param('storeId'), user.id);
  if (!owned) return c.json({ error: 'Store not found' }, 404);

  const [updated] = await db
    .update(product)
    .set({ isActive: false, updatedAt: new Date() })
    .where(and(eq(product.id, c.req.param('productId')), eq(product.storeId, owned.id)))
    .returning();

  if (!updated) return c.json({ error: 'Product not found' }, 404);
  return c.json({ message: 'Product deactivated' });
});

export default router;
