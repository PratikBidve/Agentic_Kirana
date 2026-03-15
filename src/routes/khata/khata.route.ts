import { createRouter } from '@/lib/create-app';
import { createDb } from '@/db';
import { customer, khataEntry, store } from '@/db/schema';
import { eq, and, sum, desc } from 'drizzle-orm';
import { z } from 'zod';

const router = createRouter();

const CreateCustomerSchema = z.object({
  name: z.string().min(1).max(200),
  phone: z
    .string()
    .regex(/^[6-9]\d{9}$/, 'Enter valid 10-digit Indian mobile number')
    .optional(),
});

const KhataEntrySchema = z.object({
  customerId: z.string().uuid(),
  amount: z.number().refine((v) => v !== 0, 'Amount cannot be zero'),
  note: z.string().max(500).optional(),
  // amount > 0 = credit given (customer owes you)
  // amount < 0 = payment received from customer
});

const ConfirmEntrySchema = z.object({
  confirmedByOwner: z.literal(true),
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

// ─── Customers ──────────────────────────────────────────────────────────────

/**
 * POST /api/stores/:storeId/customers
 * Add a khata customer
 */
router.post('/api/stores/:storeId/customers', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const body = await c.req.json();
  const parsed = CreateCustomerSchema.safeParse(body);
  if (!parsed.success) return c.json({ error: 'Validation failed', details: parsed.error.flatten() }, 400);

  const db = createDb(c.env);
  const owned = await verifyStoreOwner(db, c.req.param('storeId'), user.id);
  if (!owned) return c.json({ error: 'Store not found' }, 404);

  const id = crypto.randomUUID();
  await db.insert(customer).values({ id, storeId: owned.id, ...parsed.data });
  const [created] = await db.select().from(customer).where(eq(customer.id, id)).limit(1);
  return c.json(created, 201);
});

/**
 * GET /api/stores/:storeId/customers
 * List all customers with outstanding balance
 */
router.get('/api/stores/:storeId/customers', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const db = createDb(c.env);
  const owned = await verifyStoreOwner(db, c.req.param('storeId'), user.id);
  if (!owned) return c.json({ error: 'Store not found' }, 404);

  const customers = await db
    .select()
    .from(customer)
    .where(eq(customer.storeId, owned.id))
    .orderBy(desc(customer.totalOutstanding));

  return c.json(customers);
});

// ─── Khata Entries ──────────────────────────────────────────────────────────

/**
 * POST /api/stores/:storeId/khata
 * Add a khata entry (debit or credit)
 * AI agent creates entries with confirmedByOwner: false
 * Owner manually confirms via PATCH /khata/:entryId/confirm
 */
router.post('/api/stores/:storeId/khata', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const body = await c.req.json();
  const parsed = KhataEntrySchema.safeParse(body);
  if (!parsed.success) return c.json({ error: 'Validation failed', details: parsed.error.flatten() }, 400);

  const db = createDb(c.env);
  const owned = await verifyStoreOwner(db, c.req.param('storeId'), user.id);
  if (!owned) return c.json({ error: 'Store not found' }, 404);

  // Verify customer belongs to this store
  const [cust] = await db
    .select()
    .from(customer)
    .where(and(eq(customer.id, parsed.data.customerId), eq(customer.storeId, owned.id)))
    .limit(1);
  if (!cust) return c.json({ error: 'Customer not found in this store' }, 404);

  const id = crypto.randomUUID();
  await db.insert(khataEntry).values({
    id,
    storeId: owned.id,
    customerId: cust.id,
    amount: String(parsed.data.amount),
    note: parsed.data.note,
    confirmedByOwner: false, // always unconfirmed until owner approves
  });

  const [created] = await db.select().from(khataEntry).where(eq(khataEntry.id, id)).limit(1);
  return c.json(created, 201);
});

/**
 * GET /api/stores/:storeId/khata/:customerId
 * Get all ledger entries for a specific customer
 */
router.get('/api/stores/:storeId/khata/:customerId', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const db = createDb(c.env);
  const owned = await verifyStoreOwner(db, c.req.param('storeId'), user.id);
  if (!owned) return c.json({ error: 'Store not found' }, 404);

  const entries = await db
    .select()
    .from(khataEntry)
    .where(
      and(
        eq(khataEntry.storeId, owned.id),
        eq(khataEntry.customerId, c.req.param('customerId'))
      )
    )
    .orderBy(desc(khataEntry.createdAt));

  // Compute live balance from confirmed entries
  const [balanceRow] = await db
    .select({ balance: sum(khataEntry.amount) })
    .from(khataEntry)
    .where(
      and(
        eq(khataEntry.storeId, owned.id),
        eq(khataEntry.customerId, c.req.param('customerId')),
        eq(khataEntry.confirmedByOwner, true)
      )
    );

  return c.json({
    entries,
    confirmedBalance: balanceRow?.balance ?? '0',
  });
});

/**
 * PATCH /api/stores/:storeId/khata/:entryId/confirm
 * Human-in-the-loop: Owner confirms an AI-created khata entry
 * Only after confirmation does it count toward the customer balance
 */
router.patch('/api/stores/:storeId/khata/:entryId/confirm', async (c) => {
  const user = c.get('user');
  if (!user) return c.json({ error: 'Unauthorized' }, 401);

  const body = await c.req.json();
  const parsed = ConfirmEntrySchema.safeParse(body);
  if (!parsed.success) return c.json({ error: 'Validation failed', details: parsed.error.flatten() }, 400);

  const db = createDb(c.env);
  const owned = await verifyStoreOwner(db, c.req.param('storeId'), user.id);
  if (!owned) return c.json({ error: 'Store not found' }, 404);

  const [entry] = await db
    .select()
    .from(khataEntry)
    .where(and(eq(khataEntry.id, c.req.param('entryId')), eq(khataEntry.storeId, owned.id)))
    .limit(1);

  if (!entry) return c.json({ error: 'Entry not found' }, 404);
  if (entry.confirmedByOwner) return c.json({ error: 'Entry already confirmed' }, 409);

  const [confirmed] = await db
    .update(khataEntry)
    .set({ confirmedByOwner: true })
    .where(eq(khataEntry.id, entry.id))
    .returning();

  // Update cached balance on customer record
  await db
    .update(customer)
    .set({
      totalOutstanding: String(
        parseFloat(entry.amount) +
        parseFloat((await db.select({ b: sum(khataEntry.amount) })
          .from(khataEntry)
          .where(and(eq(khataEntry.customerId, entry.customerId), eq(khataEntry.confirmedByOwner, true)))
          .then(r => r[0]?.b ?? '0'))
        )
      ),
      updatedAt: new Date(),
    })
    .where(eq(customer.id, entry.customerId));

  return c.json(confirmed);
});

export default router;
