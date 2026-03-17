# Python Worker — Local Development Guide

Everything you need to run, test, and debug the `python_worker` locally.

---

## Project Structure

```
python_worker/
├── main.py                    # FastAPI app factory + lifecycle hooks
├── requirements.txt           # Pinned deps (prod + dev)
├── .env.example               # Copy to .env and fill in values
├── DEVELOPMENT.md             # This file
│
├── app/
│   ├── core/
│   │   ├── config.py          # Pydantic-settings — all env vars validated here
│   │   └── logging.py         # Structured logging setup
│   │
│   ├── db/
│   │   └── queries.py         # All asyncpg SQL queries — single source of truth
│   │
│   ├── agent/
│   │   ├── state.py           # KiranaState TypedDict (LangGraph state)
│   │   ├── llm.py             # LLM singleton (cached, shared)
│   │   ├── nodes.py           # One function per intent handler
│   │   └── graph.py           # LangGraph graph assembly + compile
│   │
│   ├── services/
│   │   └── whatsapp.py        # Meta Cloud API outbound message sender
│   │
│   ├── worker/
│   │   └── queue.py           # Redis BRPOP loop + job processor
│   │
│   └── api/
│       └── routes.py          # FastAPI routes (health + WA webhook)
│
└── tests/
    ├── test_nodes.py          # Unit tests for all LangGraph nodes
    └── test_whatsapp.py       # Unit tests for WhatsApp service
```

---

## Prerequisites

- Python 3.11+
- Docker (for Postgres + Redis)
- A valid OpenAI API key

---

## 1. First-Time Setup

```bash
cd python_worker

# Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1

# Install all dependencies (prod + dev)
pip install -r requirements.txt

# Copy env file and fill in values
cp .env.example .env
```

Open `.env` and fill in at minimum:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/kirana
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=sk-...
```

---

## 2. Start Postgres + Redis

From the **repo root** (not python_worker):

```bash
bun run docker:up
```

This starts Postgres 17 on `localhost:5432` and Redis 7 on `localhost:6379`.

Verify:
```bash
docker ps
# Should show: agentic_kirana_postgres, agentic_kirana_redis
```

---

## 3. Apply Database Schema

From the **repo root**:

```bash
bun run db:push
```

This pushes the Drizzle schema (stores, products, customers, khata_entry, agent_job tables) to your local Postgres.

---

## 4. Start the Worker

```bash
cd python_worker
source .venv/bin/activate

uvicorn main:app --reload --port 8000
```

You should see:
```
INFO: Uvicorn running on http://0.0.0.0:8000
INFO: Startup complete — worker listening
INFO: Worker loop started — listening on 'agent_jobs'
```

Verify health:
```bash
curl http://localhost:8000/health
# {"status": "ok", "version": "2.0.0"}
```

---

## 5. Run Tests

```bash
cd python_worker
source .venv/bin/activate

pytest tests/ -v
```

Expected output:
```
tests/test_nodes.py::test_detect_intent_stock_query PASSED
tests/test_nodes.py::test_detect_intent_unknown_fallback PASSED
tests/test_nodes.py::test_handle_stock_query_found PASSED
tests/test_nodes.py::test_handle_stock_query_not_found PASSED
tests/test_nodes.py::test_handle_low_stock_alert_items_found PASSED
tests/test_nodes.py::test_handle_low_stock_alert_all_healthy PASSED
tests/test_nodes.py::test_handle_inventory_update_success PASSED
tests/test_nodes.py::test_handle_inventory_update_bad_json PASSED
tests/test_nodes.py::test_handle_unknown PASSED
tests/test_whatsapp.py::test_send_message_skips_when_no_credentials PASSED
tests/test_whatsapp.py::test_send_message_calls_meta_api PASSED
```

> Tests mock all LLM and DB calls — no real API keys or DB needed to run them.

---

## 6. Manual End-to-End Test (No WhatsApp)

With worker running, test the full job pipeline via the Hono gateway:

### Step 1 — Create a store (Hono gateway on port 3000)
```bash
curl -X POST http://localhost:3000/api/stores \
  -H "Content-Type: application/json" \
  -d '{"name": "Ram Kirana", "phone": "919876543210"}'
```
Save the returned `id` as `STORE_ID`.

### Step 2 — Add a product
```bash
curl -X POST http://localhost:3000/api/stores/$STORE_ID/products \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Rice",
    "nameAliases": "chawal,rice",
    "unit": "kg",
    "currentStock": 50,
    "reorderLevel": 10,
    "sellingPrice": 40
  }'
```

### Step 3 — Send an agent message
```bash
curl -X POST http://localhost:3000/api/agent/message \
  -H "Content-Type: application/json" \
  -d '{"storeId": "'$STORE_ID'", "message": "Kitna chawal bacha hai?"}'
# Returns: {"jobId": "...", "status": "pending"}
```
Save `jobId`.

### Step 4 — Poll for result
```bash
curl http://localhost:3000/api/agent/status/$JOB_ID
# Wait 2-3 seconds, then:
# {"status": "done", "output": "Rice: 50 kg in stock."}
```

---

## 7. Test WhatsApp Webhook Locally (ngrok)

To test the inbound WhatsApp flow without deploying:

```bash
# Install ngrok if not already: https://ngrok.com
ngrok http 8000
# Copy the https URL, e.g. https://abc123.ngrok.io
```

In Meta App Dashboard:
- Go to WhatsApp → Configuration → Webhook
- Set URL: `https://abc123.ngrok.io/webhook/whatsapp`
- Set Verify Token: `kirana_verify` (or your `WA_VERIFY_TOKEN`)
- Subscribe to: `messages`

Then send a WhatsApp message from your test number to the Meta test number.
Watch worker logs — you should see the job enqueued and processed.

---

## 8. Common Errors

| Error | Cause | Fix |
|---|---|---|
| `RuntimeError: DB pool not initialised` | Nodes called before startup | Always start via `uvicorn main:app`, not by importing nodes directly |
| `ValidationError: DATABASE_URL` | `.env` not filled in | Copy `.env.example` → `.env` and fill `DATABASE_URL` |
| `asyncpg.exceptions.UndefinedTableError` | Schema not pushed | Run `bun run db:push` from repo root |
| `openai.AuthenticationError` | Invalid API key | Check `OPENAI_API_KEY` in `.env` |
| `redis.exceptions.ConnectionError` | Redis not running | Run `bun run docker:up` from repo root |
| `403` on webhook verify | Wrong verify token | Check `WA_VERIFY_TOKEN` matches Meta dashboard |

---

## 9. Adding a New Intent

1. Add the intent label to `detect_intent` prompt in `app/agent/nodes.py`
2. Write a new handler function `handle_<intent>(state)` in `nodes.py`
3. Register the node and edge in `app/agent/graph.py`
4. Write tests in `tests/test_nodes.py`

That's it — no other files need changing.

---

## 10. Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | ✅ | — | PostgreSQL connection string |
| `REDIS_URL` | ✅ | `redis://localhost:6379` | Redis connection string |
| `OPENAI_API_KEY` | ✅ | — | OpenAI API key |
| `OPENAI_MODEL` | — | `gpt-4o-mini` | LLM model name |
| `OPENAI_TEMPERATURE` | — | `0.0` | LLM temperature |
| `ENV` | — | `development` | `development` hides `/docs` in prod |
| `LOG_LEVEL` | — | `INFO` | Python logging level |
| `WA_PHONE_NUMBER_ID` | ⚠️ WA only | — | Meta phone number ID |
| `WA_ACCESS_TOKEN` | ⚠️ WA only | — | Meta permanent access token |
| `WA_VERIFY_TOKEN` | ⚠️ WA only | `kirana_verify` | Webhook verification token |
