import asyncio
import json
import os
import logging
from typing import TypedDict, Annotated

import redis.asyncio as aioredis
from fastapi import FastAPI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv
import asyncpg

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic Kirana Worker", version="1.0.0")

# ─── LangGraph State ──────────────────────────────────────────────────────

class KiranaState(TypedDict):
    messages: Annotated[list, add_messages]
    job_id: str
    store_id: str
    intent: str          # detected intent: inventory_update | khata_entry | stock_query | unknown
    confirmed: bool      # human-in-the-loop confirmation received
    result: str          # final response to send back to user

# ─── LLM ──────────────────────────────────────────────────────────────

llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0,
)

# ─── Graph Nodes ─────────────────────────────────────────────────────────

async def detect_intent(state: KiranaState) -> KiranaState:
    """Node 1: Classify user intent from raw message"""
    user_message = state["messages"][-1].content
    prompt = f"""You are an AI assistant for a small Indian kirana (grocery) store.
    Classify the following message into exactly one intent:
    - inventory_update: adding stock, updating quantity, restock
    - khata_entry: credit/debit to customer ledger, payment received
    - stock_query: asking about current stock levels
    - unknown: anything else
    
    Message: {user_message}
    
    Reply with only the intent label, nothing else."""
    
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    intent = response.content.strip().lower()
    if intent not in ["inventory_update", "khata_entry", "stock_query"]:
        intent = "unknown"
    
    logger.info(f"[{state['job_id']}] Intent detected: {intent}")
    return {**state, "intent": intent}


async def handle_stock_query(state: KiranaState) -> KiranaState:
    """Node 2a: Answer stock level questions from DB"""
    # TODO: Query products table via asyncpg for store_id
    # For now returns placeholder
    result = "Stock query feature: connect to your PostgreSQL products table here."
    return {**state, "result": result}


async def handle_inventory_update(state: KiranaState) -> KiranaState:
    """Node 2b: Parse and stage an inventory update (requires human confirmation)"""
    user_message = state["messages"][-1].content
    prompt = f"""Extract inventory update details from this message.
    Return JSON with fields: product_name, quantity, unit, action (add|set).
    Message: {user_message}
    Return only valid JSON, no explanation."""
    
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    result = f"Inventory update staged (awaiting owner confirmation): {response.content}"
    return {**state, "result": result, "confirmed": False}


async def handle_khata_entry(state: KiranaState) -> KiranaState:
    """Node 2c: Parse and stage a khata entry (requires human confirmation)"""
    user_message = state["messages"][-1].content
    prompt = f"""Extract khata (credit ledger) entry details from this message.
    Return JSON with fields: customer_name, amount (positive=credit given, negative=payment received), note.
    Message: {user_message}
    Return only valid JSON, no explanation."""
    
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    result = f"Khata entry staged (awaiting owner confirmation): {response.content}"
    return {**state, "result": result, "confirmed": False}


async def handle_unknown(state: KiranaState) -> KiranaState:
    """Node 2d: Graceful fallback for unrecognised intents"""
    result = "Sorry, I did not understand that. You can ask me to: update stock, record a khata entry, or check stock levels."
    return {**state, "result": result}


def route_by_intent(state: KiranaState) -> str:
    """Conditional edge: route to correct handler based on detected intent"""
    return state.get("intent", "unknown")


# ─── Build Graph ─────────────────────────────────────────────────────────

def build_kirana_graph():
    graph = StateGraph(KiranaState)

    graph.add_node("detect_intent", detect_intent)
    graph.add_node("stock_query", handle_stock_query)
    graph.add_node("inventory_update", handle_inventory_update)
    graph.add_node("khata_entry", handle_khata_entry)
    graph.add_node("unknown", handle_unknown)

    graph.set_entry_point("detect_intent")

    graph.add_conditional_edges(
        "detect_intent",
        route_by_intent,
        {
            "stock_query": "stock_query",
            "inventory_update": "inventory_update",
            "khata_entry": "khata_entry",
            "unknown": "unknown",
        },
    )

    graph.add_edge("stock_query", END)
    graph.add_edge("inventory_update", END)
    graph.add_edge("khata_entry", END)
    graph.add_edge("unknown", END)

    return graph.compile()


kirana_graph = build_kirana_graph()

# ─── Redis Worker Loop ──────────────────────────────────────────────────────

async def update_job_status(
    pg_pool: asyncpg.Pool,
    job_id: str,
    status: str,
    output: str | None = None,
    error: str | None = None,
):
    await pg_pool.execute(
        """UPDATE agent_job 
           SET status=$1, output=$2, error_message=$3, updated_at=NOW()
           WHERE id=$4""",
        status, output, error, job_id
    )


async def process_job(pg_pool: asyncpg.Pool, job_data: dict):
    job_id = job_data["jobId"]
    store_id = job_data["storeId"]
    message = job_data["input"]

    logger.info(f"Processing job {job_id} for store {store_id}")
    await update_job_status(pg_pool, job_id, "processing")

    try:
        initial_state: KiranaState = {
            "messages": [HumanMessage(content=message)],
            "job_id": job_id,
            "store_id": store_id,
            "intent": "",
            "confirmed": False,
            "result": "",
        }
        final_state = await kirana_graph.ainvoke(initial_state)
        await update_job_status(pg_pool, job_id, "done", output=final_state["result"])
        logger.info(f"Job {job_id} completed: {final_state['result'][:100]}")
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        await update_job_status(pg_pool, job_id, "failed", error=str(e))


async def worker_loop():
    """Blocking Redis BRPOP loop — processes one job at a time"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    db_url = os.getenv("DATABASE_URL")

    redis_client = await aioredis.from_url(redis_url)
    pg_pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)

    logger.info("Kirana worker started. Listening on Redis queue: agent_jobs")

    while True:
        try:
            # BRPOP blocks until a job arrives — timeout 5s to allow graceful shutdown
            result = await redis_client.brpop("agent_jobs", timeout=5)
            if result:
                _, raw = result
                job_data = json.loads(raw)
                await process_job(pg_pool, job_data)
        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            await asyncio.sleep(1)


@app.on_event("startup")
async def startup():
    asyncio.create_task(worker_loop())


@app.get("/health")
async def health():
    return {"status": "ok", "worker": "running"}
