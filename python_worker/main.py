import asyncio
import json
import os
import logging
import re
from typing import TypedDict, Annotated, Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, Request, Response
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
import asyncpg
import httpx

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic Kirana Worker", version="2.0.0")

# ─── LangGraph State ──────────────────────────────────────────────────────────

class KiranaState(TypedDict):
    messages: Annotated[list, add_messages]
    job_id: str
    store_id: str
    intent: str
    confirmed: bool
    result: str
    db_payload: dict          # structured data extracted for DB write
    wa_phone: Optional[str]   # WhatsApp reply-to phone number (E.164)

# ─── LLM ─────────────────────────────────────────────────────────────────────

llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0,
)

# ─── DB Helpers ───────────────────────────────────────────────────────────────

async def get_pg_pool() -> asyncpg.Pool:
    """Module-level pool — created once at startup."""
    return app.state.pg_pool


async def fuzzy_find_product(
    pool: asyncpg.Pool,
    store_id: str,
    name: str
) -> Optional[dict]:
    """
    Find product by exact name first, then aliases.
    Returns first match or None. Case-insensitive.
    """
    row = await pool.fetchrow(
        """
        SELECT id, name, current_stock, unit, selling_price, reorder_level
        FROM product
        WHERE store_id = $1
          AND is_active = true
          AND (lower(name) = lower($2)
               OR lower(name_aliases) LIKE lower($3))
        LIMIT 1
        """,
        store_id, name, f"%{name}%"
    )
    return dict(row) if row else None


async def fuzzy_find_customer(
    pool: asyncpg.Pool,
    store_id: str,
    name: str
) -> Optional[dict]:
    """Find customer by name (case-insensitive partial match)."""
    row = await pool.fetchrow(
        """
        SELECT id, name, phone, total_outstanding
        FROM customer
        WHERE store_id = $1
          AND lower(name) LIKE lower($2)
        LIMIT 1
        """,
        store_id, f"%{name}%"
    )
    return dict(row) if row else None

# ─── Graph Nodes ──────────────────────────────────────────────────────────────

async def detect_intent(state: KiranaState) -> KiranaState:
    """Node 1: Classify user intent. Handles Hindi/Marathi/English mixed text."""
    user_message = state["messages"][-1].content
    prompt = f"""You are an AI assistant for a small Indian kirana (grocery) store.
Classify the following message into exactly one intent:
- inventory_update: adding stock, restocking, quantity update
- khata_entry: credit/debit to customer ledger, udhaar, payment received
- stock_query: asking about current stock levels, kitna bacha hai
- low_stock_alert: asking which items are running low
- unknown: anything else

Message: {user_message}

Reply with only the intent label, nothing else."""

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    intent = response.content.strip().lower()
    valid = {"inventory_update", "khata_entry", "stock_query", "low_stock_alert"}
    if intent not in valid:
        intent = "unknown"

    logger.info(f"[{state['job_id']}] Intent: {intent}")
    return {**state, "intent": intent}


async def handle_stock_query(state: KiranaState) -> KiranaState:
    """Node 2a: Query live stock from DB, scoped to store."""
    user_message = state["messages"][-1].content
    pool = await get_pg_pool()

    # Extract product name from message
    extract_prompt = f"""Extract the product name being asked about from this message.
Return only the product name, nothing else. If unclear, return 'all'.
Message: {user_message}"""
    name_resp = await llm.ainvoke([HumanMessage(content=extract_prompt)])
    product_name = name_resp.content.strip()

    if product_name.lower() == "all":
        rows = await pool.fetch(
            """
            SELECT name, current_stock, unit, reorder_level
            FROM product
            WHERE store_id = $1 AND is_active = true
            ORDER BY name
            """,
            state["store_id"]
        )
        if not rows:
            result = "No products found in your inventory."
        else:
            lines = [f"• {r['name']}: {r['current_stock']} {r['unit']}" for r in rows]
            result = "Current stock:\n" + "\n".join(lines)
    else:
        prod = await fuzzy_find_product(pool, state["store_id"], product_name)
        if prod:
            result = f"{prod['name']}: {prod['current_stock']} {prod['unit']} in stock."
            if float(prod['current_stock']) <= float(prod['reorder_level'] or 0):
                result += " ⚠️ Low stock — time to reorder."
        else:
            result = f"Product '{product_name}' not found in your inventory."

    return {**state, "result": result}


async def handle_low_stock_alert(state: KiranaState) -> KiranaState:
    """Node 2b: List all items below reorder level."""
    pool = await get_pg_pool()
    rows = await pool.fetch(
        """
        SELECT name, current_stock, unit, reorder_level
        FROM product
        WHERE store_id = $1
          AND is_active = true
          AND reorder_level IS NOT NULL
          AND reorder_level > 0
          AND current_stock <= reorder_level
        ORDER BY current_stock ASC
        """,
        state["store_id"]
    )
    if not rows:
        result = "✅ All items are above reorder level. Stock is healthy."
    else:
        lines = [f"• {r['name']}: {r['current_stock']}/{r['reorder_level']} {r['unit']}" for r in rows]
        result = f"⚠️ {len(rows)} items need restocking:\n" + "\n".join(lines)

    return {**state, "result": result}


async def handle_inventory_update(state: KiranaState) -> KiranaState:
    """Node 2c: Parse inventory update and STAGE it in DB (confirmedByOwner=false)."""
    user_message = state["messages"][-1].content
    pool = await get_pg_pool()

    extract_prompt = f"""Extract inventory update from this message.
Return valid JSON with fields:
  product_name (string),
  quantity (number, always positive),
  action ("add" to add to stock, "set" to set exact value)
No explanation, only JSON.
Message: {user_message}"""

    response = await llm.ainvoke([HumanMessage(content=extract_prompt)])
    raw = response.content.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"```(?:json)?\n?", "", raw).strip()

    try:
        payload = json.loads(raw)
        product_name = payload["product_name"]
        quantity = float(payload["quantity"])
        action = payload.get("action", "add")
    except Exception:
        return {**state, "result": f"Could not parse inventory update. Please say something like: 'Add 10 kg rice' or 'Set sugar to 25 kg'."}

    prod = await fuzzy_find_product(pool, state["store_id"], product_name)
    if not prod:
        return {**state, "result": f"Product '{product_name}' not found. Add it to inventory first via the dashboard."}

    current = float(prod["current_stock"])
    new_stock = (current + quantity) if action == "add" else quantity

    # Stage the update as an agent_job output — actual write happens after owner confirms
    # Store structured payload for the confirm endpoint to use
    db_payload = {
        "type": "inventory_update",
        "product_id": prod["id"],
        "product_name": prod["name"],
        "old_stock": current,
        "new_stock": new_stock,
        "action": action,
        "quantity": quantity,
    }

    result = (
        f"📦 Staged: {prod['name']} stock {'increased by' if action == 'add' else 'set to'} "
        f"{quantity if action == 'add' else new_stock} {prod['unit']}. "
        f"New total would be {new_stock} {prod['unit']}.\n"
        f"Reply 'confirm' to apply, or 'cancel' to discard."
    )
    return {**state, "result": result, "confirmed": False, "db_payload": db_payload}


async def handle_khata_entry(state: KiranaState) -> KiranaState:
    """Node 2d: Parse khata entry and create it in DB with confirmedByOwner=false."""
    user_message = state["messages"][-1].content
    pool = await get_pg_pool()

    extract_prompt = f"""Extract khata (credit ledger) details from this message.
Return valid JSON with fields:
  customer_name (string),
  amount (number: positive = udhaar/credit given, negative = payment received),
  note (string, brief description)
No explanation, only JSON.
Message: {user_message}"""

    response = await llm.ainvoke([HumanMessage(content=extract_prompt)])
    raw = response.content.strip()
    raw = re.sub(r"```(?:json)?\n?", "", raw).strip()

    try:
        payload = json.loads(raw)
        customer_name = payload["customer_name"]
        amount = float(payload["amount"])
        note = payload.get("note", "")
    except Exception:
        return {**state, "result": "Could not parse khata entry. Try: 'Ramesh ne 200 rupay liye' or 'Sunita ne 500 diye'."}

    cust = await fuzzy_find_customer(pool, state["store_id"], customer_name)
    if not cust:
        return {**state, "result": f"Customer '{customer_name}' not found. Add them first via the dashboard."}

    # Create staged khata entry (confirmedByOwner = false)
    entry_id = __import__('uuid').uuid4()
    await pool.execute(
        """
        INSERT INTO khata_entry (id, store_id, customer_id, amount, note, confirmed_by_owner, created_at)
        VALUES ($1, $2, $3, $4, $5, false, NOW())
        """,
        str(entry_id), state["store_id"], cust["id"], str(amount), note
    )

    direction = "udhaar (credit given)" if amount > 0 else "payment received"
    result = (
        f"📒 Staged: {cust['name']} — ₹{abs(amount)} {direction}.\n"
        f"Note: {note}\n"
        f"Reply 'confirm {entry_id}' to apply to ledger."
    )
    db_payload = {"type": "khata_entry", "entry_id": str(entry_id), "customer_id": cust["id"]}
    return {**state, "result": result, "confirmed": False, "db_payload": db_payload}


async def handle_unknown(state: KiranaState) -> KiranaState:
    result = (
        "Sorry, I didn't understand that.\n"
        "You can ask me to:\n"
        "• Check stock: 'Kitna chawal bacha hai?'\n"
        "• Update stock: 'Add 10 kg sugar'\n"
        "• Khata: 'Ramesh ne 200 ka maal liya'\n"
        "• Low stock: 'Kya khatam ho raha hai?'"
    )
    return {**state, "result": result}


def route_by_intent(state: KiranaState) -> str:
    return state.get("intent", "unknown")


# ─── Build Graph ──────────────────────────────────────────────────────────────

def build_kirana_graph():
    graph = StateGraph(KiranaState)

    graph.add_node("detect_intent", detect_intent)
    graph.add_node("stock_query", handle_stock_query)
    graph.add_node("low_stock_alert", handle_low_stock_alert)
    graph.add_node("inventory_update", handle_inventory_update)
    graph.add_node("khata_entry", handle_khata_entry)
    graph.add_node("unknown", handle_unknown)

    graph.set_entry_point("detect_intent")
    graph.add_conditional_edges(
        "detect_intent",
        route_by_intent,
        {
            "stock_query": "stock_query",
            "low_stock_alert": "low_stock_alert",
            "inventory_update": "inventory_update",
            "khata_entry": "khata_entry",
            "unknown": "unknown",
        },
    )
    for node in ["stock_query", "low_stock_alert", "inventory_update", "khata_entry", "unknown"]:
        graph.add_edge(node, END)

    return graph.compile()


kirana_graph = build_kirana_graph()

# ─── WhatsApp Outbound ────────────────────────────────────────────────────────

async def send_whatsapp_reply(to_phone: str, message: str):
    """
    Send reply back to WhatsApp using Meta Cloud API.
    Requires WA_PHONE_NUMBER_ID and WA_ACCESS_TOKEN in env.
    """
    phone_id = os.getenv("WA_PHONE_NUMBER_ID")
    token = os.getenv("WA_ACCESS_TOKEN")
    if not phone_id or not token:
        logger.warning("WhatsApp env vars not set — skipping outbound reply")
        return

    url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": message},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        if resp.status_code != 200:
            logger.error(f"WhatsApp send failed: {resp.status_code} {resp.text}")
        else:
            logger.info(f"WhatsApp reply sent to {to_phone}")


# ─── Redis Worker ─────────────────────────────────────────────────────────────

async def update_job_status(
    pool: asyncpg.Pool,
    job_id: str,
    status: str,
    output: str = None,
    error: str = None,
    db_payload: dict = None,
):
    await pool.execute(
        """
        UPDATE agent_job
        SET status=$1, output=$2, error_message=$3,
            agent_steps=$4, updated_at=NOW()
        WHERE id=$5
        """,
        status,
        output,
        error,
        json.dumps(db_payload) if db_payload else None,
        job_id,
    )


async def process_job(pool: asyncpg.Pool, job_data: dict):
    job_id = job_data["jobId"]
    store_id = job_data["storeId"]
    message = job_data["input"]
    wa_phone = job_data.get("waPhone")  # optional — set by WhatsApp webhook

    logger.info(f"Processing job {job_id} for store {store_id}")
    await update_job_status(pool, job_id, "processing")

    try:
        initial_state: KiranaState = {
            "messages": [HumanMessage(content=message)],
            "job_id": job_id,
            "store_id": store_id,
            "intent": "",
            "confirmed": False,
            "result": "",
            "db_payload": {},
            "wa_phone": wa_phone,
        }
        final_state = await kirana_graph.ainvoke(initial_state)
        output = final_state["result"]
        db_payload = final_state.get("db_payload", {})

        await update_job_status(pool, job_id, "done", output=output, db_payload=db_payload)
        logger.info(f"Job {job_id} done")

        # Push reply back to WhatsApp if originated from WA
        if wa_phone and output:
            await send_whatsapp_reply(wa_phone, output)

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
        await update_job_status(pool, job_id, "failed", error=str(e))


async def worker_loop():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_client = await aioredis.from_url(redis_url)
    pool: asyncpg.Pool = app.state.pg_pool

    logger.info("Kirana worker v2 started — listening on agent_jobs")

    while True:
        try:
            result = await redis_client.brpop("agent_jobs", timeout=5)
            if result:
                _, raw = result
                job_data = json.loads(raw)
                # Process concurrently — don't block loop on slow LLM calls
                asyncio.create_task(process_job(pool, job_data))
        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            await asyncio.sleep(1)


# ─── WhatsApp Webhook ─────────────────────────────────────────────────────────

@app.get("/webhook/whatsapp")
async def whatsapp_verify(request: Request):
    """
    Meta webhook verification challenge.
    Set WA_VERIFY_TOKEN in env to match what you set in Meta App Dashboard.
    """
    params = request.query_params
    verify_token = os.getenv("WA_VERIFY_TOKEN", "kirana_verify")
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == verify_token
    ):
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Receive inbound WhatsApp messages from Meta Cloud API.
    Extracts phone + message text, creates agent_job, enqueues to Redis.
    """
    body = await request.json()
    redis_client = app.state.redis_client
    pool: asyncpg.Pool = app.state.pg_pool

    try:
        entry = body["entry"][0]
        change = entry["changes"][0]["value"]
        messages = change.get("messages", [])
        if not messages:
            return {"status": "no_message"}  # status update / delivery receipt

        msg = messages[0]
        wa_phone = msg["from"]  # E.164 format e.g. "919876543210"
        text = msg.get("text", {}).get("body", "").strip()

        if not text:
            return {"status": "non_text_ignored"}

        # Look up store by WhatsApp phone number
        row = await pool.fetchrow(
            "SELECT id FROM store WHERE phone = $1 LIMIT 1",
            wa_phone
        )
        if not row:
            logger.warning(f"Unregistered WA number: {wa_phone}")
            return {"status": "store_not_found"}

        store_id = row["id"]
        job_id = str(__import__('uuid').uuid4())

        # Persist job
        await pool.execute(
            """
            INSERT INTO agent_job (id, store_id, input, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'pending', NOW(), NOW())
            """,
            job_id, store_id, text
        )

        # Enqueue with wa_phone for reply routing
        payload = json.dumps({
            "jobId": job_id,
            "storeId": store_id,
            "input": text,
            "waPhone": wa_phone,
        })
        await redis_client.lpush("agent_jobs", payload)

        logger.info(f"WA job {job_id} enqueued for store {store_id}")
        return {"status": "queued", "job_id": job_id}

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        # Always return 200 to Meta or they'll retry aggressively
        return {"status": "error"}


# ─── Lifecycle ────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    db_url = os.getenv("DATABASE_URL")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    app.state.pg_pool = await asyncpg.create_pool(
        db_url, min_size=2, max_size=10, command_timeout=30
    )
    app.state.redis_client = await aioredis.from_url(redis_url)

    asyncio.create_task(worker_loop())
    logger.info("Startup complete")


@app.on_event("shutdown")
async def shutdown():
    await app.state.pg_pool.close()
    await app.state.redis_client.close()


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
