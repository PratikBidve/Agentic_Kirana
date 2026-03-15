import {
  pgTable,
  text,
  timestamp,
  boolean,
  numeric,
  integer,
} from 'drizzle-orm/pg-core';

// ─── Better-Auth required tables ───────────────────────────────────────────

export const user = pgTable('user', {
  id: text('id').primaryKey(),
  name: text('name').notNull(),
  email: text('email').notNull().unique(),
  emailVerified: boolean('email_verified').notNull(),
  image: text('image'),
  createdAt: timestamp('created_at').notNull(),
  updatedAt: timestamp('updated_at').notNull(),
});

export const session = pgTable('session', {
  id: text('id').primaryKey(),
  expiresAt: timestamp('expires_at').notNull(),
  token: text('token').notNull().unique(),
  createdAt: timestamp('created_at').notNull(),
  updatedAt: timestamp('updated_at').notNull(),
  ipAddress: text('ip_address'),
  userAgent: text('user_agent'),
  userId: text('user_id')
    .notNull()
    .references(() => user.id, { onDelete: 'cascade' }),
});

export const account = pgTable('account', {
  id: text('id').primaryKey(),
  accountId: text('account_id').notNull(),
  providerId: text('provider_id').notNull(),
  userId: text('user_id')
    .notNull()
    .references(() => user.id, { onDelete: 'cascade' }),
  accessToken: text('access_token'),
  refreshToken: text('refresh_token'),
  idToken: text('id_token'),
  accessTokenExpiresAt: timestamp('access_token_expires_at'),
  refreshTokenExpiresAt: timestamp('refresh_token_expires_at'),
  scope: text('scope'),
  password: text('password'),
  createdAt: timestamp('created_at').notNull(),
  updatedAt: timestamp('updated_at').notNull(),
});

export const verification = pgTable('verification', {
  id: text('id').primaryKey(),
  identifier: text('identifier').notNull(),
  value: text('value').notNull(),
  expiresAt: timestamp('expires_at').notNull(),
  createdAt: timestamp('created_at'),
  updatedAt: timestamp('updated_at'),
});

// ─── Kirana Business Domain ─────────────────────────────────────────────────

/**
 * store: One kirana shop = one store record, linked to owner user
 */
export const store = pgTable('store', {
  id: text('id').primaryKey(),
  ownerId: text('owner_id')
    .notNull()
    .references(() => user.id, { onDelete: 'cascade' }),
  name: text('name').notNull(),
  phone: text('phone'), // Primary WhatsApp number for agent interactions
  address: text('address'),
  gstNumber: text('gst_number'),
  createdAt: timestamp('created_at').notNull().defaultNow(),
  updatedAt: timestamp('updated_at').notNull().defaultNow(),
});

/**
 * product: Inventory item in a store
 * nameAliases: comma-separated alternate names (e.g. "Parle-G,PG biscuit,parleg")
 * for fuzzy matching before you add pgvector embeddings
 */
export const product = pgTable('product', {
  id: text('id').primaryKey(),
  storeId: text('store_id')
    .notNull()
    .references(() => store.id, { onDelete: 'cascade' }),
  name: text('name').notNull(),
  nameAliases: text('name_aliases'), // Fuzzy match aliases
  unit: text('unit').notNull(), // kg | piece | litre | dozen | pack
  currentStock: numeric('current_stock').notNull().default('0'),
  reorderLevel: numeric('reorder_level').default('0'),
  sellingPrice: numeric('selling_price').notNull(),
  costPrice: numeric('cost_price'),
  category: text('category'), // grocery | snacks | dairy | beverages | household
  isActive: boolean('is_active').notNull().default(true),
  createdAt: timestamp('created_at').notNull().defaultNow(),
  updatedAt: timestamp('updated_at').notNull().defaultNow(),
});

/**
 * customer: Khata / credit ledger customer
 */
export const customer = pgTable('customer', {
  id: text('id').primaryKey(),
  storeId: text('store_id')
    .notNull()
    .references(() => store.id, { onDelete: 'cascade' }),
  name: text('name').notNull(),
  phone: text('phone'),
  totalOutstanding: numeric('total_outstanding').notNull().default('0'), // cached balance
  createdAt: timestamp('created_at').notNull().defaultNow(),
  updatedAt: timestamp('updated_at').notNull().defaultNow(),
});

/**
 * khataEntry: Individual debit/credit ledger line
 * amount > 0 = credit given to customer (they owe you)
 * amount < 0 = payment received from customer
 */
export const khataEntry = pgTable('khata_entry', {
  id: text('id').primaryKey(),
  storeId: text('store_id')
    .notNull()
    .references(() => store.id, { onDelete: 'cascade' }),
  customerId: text('customer_id')
    .notNull()
    .references(() => customer.id, { onDelete: 'cascade' }),
  amount: numeric('amount').notNull(),
  note: text('note'),
  confirmedByOwner: boolean('confirmed_by_owner').notNull().default(false), // human-in-the-loop
  createdAt: timestamp('created_at').notNull().defaultNow(),
});

/**
 * agentJob: Bridge table between Hono edge gateway and FastAPI/LangGraph Python worker
 * Hono writes a job here + pushes to Redis queue
 * FastAPI reads Redis, processes LangGraph DAG, updates status + output here
 */
export const agentJob = pgTable('agent_job', {
  id: text('id').primaryKey(),
  storeId: text('store_id')
    .notNull()
    .references(() => store.id, { onDelete: 'cascade' }),
  status: text('status').notNull().default('pending'), // pending | processing | done | failed
  input: text('input').notNull(), // raw user message or WhatsApp text
  output: text('output'), // agent final response text
  agentSteps: text('agent_steps'), // JSON stringified LangGraph step trace for debugging
  errorMessage: text('error_message'),
  retryCount: integer('retry_count').notNull().default(0),
  createdAt: timestamp('created_at').notNull().defaultNow(),
  updatedAt: timestamp('updated_at').notNull().defaultNow(),
});
