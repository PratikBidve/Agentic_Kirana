# Agentic Kirana

An AI-powered backend system for Indian kirana (grocery) stores.
Owners can manage inventory, track customer credit (khata), and interact with an AI agent that understands natural language commands.

---

## Architecture

```
User / WhatsApp
      │
      ▼
┌─────────────────────────────────┐
│  Hono API Gateway (Bun)         │  ← Edge-fast, Cloudflare Workers
│  Auth · Store · Inventory       │
│  Khata · Agent Job Intake       │
└────────────┬────────────────────┘
             │ Redis Queue
             ▼
┌─────────────────────────────────┐
│  FastAPI + LangGraph Worker     │  ← Python AI microservice
│  Intent Detection → Routing     │
│  Inventory / Khata Agent Nodes  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  PostgreSQL                     │  ← Single source of truth
│  Stores · Products · Khata      │
│  Sessions · Agent Jobs          │
└─────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | [Bun](https://bun.sh) |
| API Framework | [Hono](https://hono.dev) |
| Auth | [Better Auth](https://www.better-auth.com) (Google OAuth) |
| ORM | [Drizzle ORM](https://orm.drizzle.team) |
| Database | PostgreSQL 17 |
| Queue | Redis 7 (via ioredis) |
| Deployment | Cloudflare Workers |
| AI Framework | [LangGraph](https://langchain-ai.github.io/langgraph/) + [LangChain](https://python.langchain.com) |
| AI Runtime | Python 3.11+ · FastAPI · asyncpg |

---

## Features

- **Store Management** — create and manage multiple kirana store profiles with GST number and Indian mobile validation
- **Inventory** — add, update, soft-delete products with unit, price, reorder level, and low-stock filtering
- **Khata (Credit Ledger)** — track customer credit/debit with human-in-the-loop owner confirmation before balance updates
- **AI Agent** — natural language commands processed via LangGraph: stock queries, inventory updates, khata entries
- **Async Job Queue** — Hono writes jobs to Redis; Python worker processes them without blocking the gateway
- **Rate Limiting** — Redis sliding window per IP (60 req/60s)
- **Edge Deployment** — Cloudflare Workers for global low-latency API

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/PratikBidve/Agentic_Kirana.git
cd Agentic_Kirana

# 2. Install JS deps
bun install

# 3. Configure environment
cp .env.example .env
# Edit .env with your values

# 4. Start Postgres + Redis
bun run docker:up

# 5. Push database schema
bun run db:push

# 6. Start API gateway
bun run dev
```

In a second terminal, start the Python AI worker:

```bash
cd python_worker
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env        # fill in OPENAI_API_KEY
uvicorn main:app --reload --port 8000
```

Verify both services are running:

```bash
curl http://localhost:3000/health   # Hono gateway
curl http://localhost:8000/health   # Python worker
```

> **Note:** Wrangler dev server runs on port `3000` by default (configured in `wrangler.jsonc`).

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `REDIS_URL` | ✅ | Redis connection string |
| `GOOGLE_CLIENT_ID` | ✅ | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | ✅ | Google OAuth client secret |
| `BETTER_AUTH_SECRET` | ✅ | Random string, min 32 chars |
| `BETTER_AUTH_URL` | ✅ | Base URL of this API (e.g. `http://localhost:3000`) |
| `ALLOWED_ORIGIN` | ✅ | Frontend URL for CORS (e.g. `http://localhost:3001`) |
| `NODE_ENV` | — | `development` / `production` (default: `development`) |

**Python worker** (in `python_worker/.env`):

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | Same PostgreSQL URL |
| `REDIS_URL` | ✅ | Same Redis URL |
| `OPENAI_API_KEY` | ✅ | OpenAI API key for LangGraph LLM |

---

## Available Commands

### Bun / JS

| Command | Description |
|---|---|
| `bun run dev` | Start local Wrangler dev server (port 3000) |
| `bun run deploy` | Deploy to Cloudflare Workers |
| `bun run cf-typegen` | Generate Cloudflare binding types |
| `bun test` | Run test suite |
| `bun run test:watch` | Watch mode tests |
| `bun run docker:up` | Start Postgres + Redis containers |
| `bun run docker:down` | Stop containers |
| `bun run docker:clean` | Stop + remove containers and volumes |
| `bun run db:push` | Push Drizzle schema to database |
| `bun run db:generate` | Generate migration files |
| `bun run db:migrate` | Run pending migrations |
| `bun run db:studio` | Open Drizzle Studio GUI |

### Python Worker

| Command | Description |
|---|---|
| `uvicorn main:app --reload --port 8000` | Start worker |
| `pip install -r requirements.txt` | Install Python deps |

---

## API Reference

See [`docs/API.md`](./docs/API.md) for the complete endpoint reference including request/response payloads, auth requirements, and error codes.

Better Auth's auto-generated OpenAPI docs are available at:
```
http://localhost:3000/api/auth/reference
```

---

## Project Structure

```
.
├── src/
│   ├── app.ts                      # Route registration
│   ├── env.ts                      # Zod-validated env schema
│   ├── env-runtime.ts              # Env loader for drizzle-kit
│   ├── db/
│   │   ├── index.ts                # Drizzle singleton (Neon HTTP)
│   │   ├── schema.ts               # All table definitions
│   │   └── migrations/             # Generated migration files
│   ├── lib/
│   │   ├── auth.ts                 # Better Auth singleton
│   │   ├── create-app.ts           # Hono app factory + middleware
│   │   ├── redis.ts                # Redis singleton + queue helpers
│   │   └── types.ts                # Strongly typed AppBindings
│   ├── middlewares/
│   │   ├── auth-cors.ts            # CORS for auth routes
│   │   ├── not-found.ts            # 404 handler
│   │   ├── on-error.ts             # Global error handler
│   │   ├── rate-limit.ts           # Redis sliding window rate limiter
│   │   └── with-session.ts         # Session injection middleware
│   └── routes/
│       ├── index.route.ts          # GET / and GET /health
│       ├── auth/auth.index.ts      # Better Auth handler
│       ├── store/store.route.ts    # Store CRUD
│       ├── inventory/inventory.route.ts  # Product CRUD + stock patch
│       ├── khata/khata.route.ts    # Customer ledger + confirmation
│       └── agent/agent.route.ts    # AI job intake + status polling
├── tests/
│   ├── store.test.ts
│   ├── inventory.test.ts
│   ├── khata.test.ts
│   └── agent.test.ts
├── python_worker/
│   ├── main.py                     # FastAPI + LangGraph worker
│   ├── requirements.txt
│   └── .env.example
├── docs/
│   └── API.md                      # Full API payload reference
├── LOCAL_DEVELOPMENT.md            # Local setup + workflow guide
├── docker-compose.yml              # Postgres 17 + Redis 7
├── drizzle.config.ts
├── wrangler.jsonc
├── package.json
├── tsconfig.json
└── .env.example
```

---

## Database Schema

| Table | Purpose |
|---|---|
| `user` | Authenticated users (Better Auth) |
| `session` | User sessions (Better Auth) |
| `account` | OAuth accounts (Better Auth) |
| `verification` | Email verification tokens (Better Auth) |
| `store` | Kirana store profile per user |
| `product` | Inventory items per store |
| `customer` | Khata (ledger) customers per store |
| `khata_entry` | Individual debit/credit entries |
| `agent_job` | AI agent jobs queue bridge |

---

## Human-in-the-Loop Design

All AI-generated financial mutations (khata entries, stock updates) are created with `confirmedByOwner: false`.
They are **staged but not applied** until the store owner explicitly confirms via:

```
PATCH /api/stores/:storeId/khata/:entryId/confirm
{ "confirmedByOwner": true }
```

This prevents AI hallucinations from corrupting financial records.

---

## Local Development

For detailed setup, daily workflow, debugging, common errors, and testing checklist — see:

📖 **[LOCAL_DEVELOPMENT.md](./LOCAL_DEVELOPMENT.md)**

---

## License

[MIT](LICENSE)
