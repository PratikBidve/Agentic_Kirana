# Agentic Kirana — API Reference

Base URL: `http://localhost:8787` (dev) | `https://your-worker.workers.dev` (prod)

All protected routes require a valid session cookie set by Better-Auth Google OAuth.

---

## Health

### `GET /`
Returns API info.
```json
{
  "name": "Agentic Kirana API",
  "version": "1.0.0",
  "status": "ok",
  "docs": "/api/auth/reference",
  "timestamp": "2026-03-15T13:00:00.000Z"
}
```

### `GET /health`
Liveness probe. Returns `200 { "status": "ok" }`. No auth required.

---

## Auth

### `GET /api/auth/reference`
Auto-generated Better-Auth OpenAPI docs (Scalar UI). Visit in browser.

### `POST /api/auth/sign-in/social`
Initiate Google OAuth flow.
```json
{ "provider": "google", "callbackURL": "/dashboard" }
```

---

## Stores

### `POST /api/stores` 🔒
Create a kirana store for the authenticated user.

**Request Body:**
```json
{
  "name": "Sharma General Store",          // required, max 200 chars
  "phone": "9876543210",                   // optional, valid Indian mobile
  "address": "123 MG Road, Mumbai 400001", // optional
  "gstNumber": "27AAPFU0939F1ZV"          // optional, valid GST format
}
```
**Response `201`:**
```json
{
  "id": "uuid",
  "ownerId": "user-uuid",
  "name": "Sharma General Store",
  "phone": "9876543210",
  "address": "123 MG Road, Mumbai 400001",
  "gstNumber": "27AAPFU0939F1ZV",
  "createdAt": "2026-03-15T13:00:00.000Z",
  "updatedAt": "2026-03-15T13:00:00.000Z"
}
```

### `GET /api/stores` 🔒
List all stores owned by authenticated user. Returns `Store[]`.

### `GET /api/stores/:storeId` 🔒
Get single store. Returns `404` if not owner.

### `PUT /api/stores/:storeId` 🔒
Partially update store. Same body shape as POST (all fields optional).

### `DELETE /api/stores/:storeId` 🔒
Permanently delete store and all associated data (cascade).

---

## Inventory

### `POST /api/stores/:storeId/products` 🔒
Add product to inventory.

**Request Body:**
```json
{
  "name": "Parle-G Biscuit",              // required
  "nameAliases": "Parle G,PG biscuit,parleg", // optional, comma-separated fuzzy aliases
  "unit": "piece",                         // required: kg|piece|litre|dozen|pack|gram|ml
  "currentStock": 200,                     // required, >= 0
  "reorderLevel": 50,                      // optional, alert threshold
  "sellingPrice": 5.00,                    // required, > 0
  "costPrice": 4.00,                       // optional
  "category": "snacks"                     // optional: grocery|snacks|dairy|beverages|household|other
}
```
**Response `201`:** Full product object.

### `GET /api/stores/:storeId/products` 🔒
List all active products.

**Query Params:**
- `?lowStock=true` — returns only products where `currentStock <= reorderLevel`

### `GET /api/stores/:storeId/products/:productId` 🔒
Get single product.

### `PUT /api/stores/:storeId/products/:productId` 🔒
Update product (all fields optional).

### `PATCH /api/stores/:storeId/products/:productId/stock` 🔒
Quick stock update — used by AI agent after confirmation.

**Request Body:**
```json
{
  "currentStock": 150,
  "note": "Restocked from Parle distributor"  // optional
}
```

### `DELETE /api/stores/:storeId/products/:productId` 🔒
Soft delete — sets `isActive = false`. Product remains in DB for audit trail.

---

## Khata (Ledger)

### `POST /api/stores/:storeId/customers` 🔒
Add a credit customer.
```json
{
  "name": "Ramesh Sharma",   // required
  "phone": "9876543210"     // optional
}
```

### `GET /api/stores/:storeId/customers` 🔒
List customers sorted by `totalOutstanding` descending (highest debtor first).

### `POST /api/stores/:storeId/khata` 🔒
Add ledger entry.

**Convention:**
- `amount > 0` = credit given to customer (they owe you money)
- `amount < 0` = payment received from customer

**Note:** All entries start as `confirmedByOwner: false`. Only confirmed entries count toward balance.

```json
{
  "customerId": "customer-uuid",  // required
  "amount": 350.00,               // required, non-zero. Positive=credit, Negative=payment
  "note": "Monthly grocery credit" // optional, max 500 chars
}
```
**Response `201`:** Full khata entry with `confirmedByOwner: false`.

### `GET /api/stores/:storeId/khata/:customerId` 🔒
Get all entries + confirmed balance for a customer.
```json
{
  "entries": [...],
  "confirmedBalance": "1250.00"  // sum of confirmed entries only
}
```

### `PATCH /api/stores/:storeId/khata/:entryId/confirm` 🔒
Human-in-the-loop confirmation. Owner approves AI-created entry.
```json
{ "confirmedByOwner": true }
```
Returns `409` if already confirmed.

---

## AI Agent

### `POST /api/agent/message`
Send a natural language message to the Kirana AI agent.

**No auth required** (rate-limited by IP via Redis).

```json
{
  "storeId": "store-uuid",
  "message": "Add 50kg sugar to stock"  // max 2000 chars
}
```
**Response `202`:** Job accepted.
```json
{
  "jobId": "uuid",
  "status": "pending"
}
```

### `GET /api/agent/status/:jobId`
Poll job status. Poll every 2s until `status` is `done` or `failed`.

```json
{
  "jobId": "uuid",
  "status": "done",             // pending | processing | done | failed
  "output": "Inventory update staged: 50kg sugar added (awaiting confirmation)",
  "error": null,
  "createdAt": "2026-03-15T13:00:00.000Z",
  "updatedAt": "2026-03-15T13:00:05.000Z"
}
```

---

## Error Responses

All errors follow this shape:
```json
{ "error": "Human readable message", "details": {} }
```

| Status | Meaning |
|---|---|
| `400` | Validation failed — check `details.fieldErrors` |
| `401` | Not authenticated — sign in via `/api/auth/sign-in/social` |
| `404` | Resource not found or you don't own it |
| `409` | Conflict (e.g. already confirmed) |
| `429` | Rate limited — slow down |
| `500` | Server error — check logs |

---

## Rate Limits

Redis sliding window: **60 requests / 60 seconds per IP**.
Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`.

---

## Running Locally

```bash
# 1. Copy env
cp .env.example .env

# 2. Start Postgres + Redis
bun run docker:up

# 3. Push schema
bun run db:push

# 4. Start Hono gateway
bun run dev

# 5. Start Python worker (separate terminal)
cd python_worker
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 6. Run tests
bun test
```
