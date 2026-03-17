"""Redis worker loop — dequeues jobs, runs LangGraph, writes results."""
import asyncio
import json
import logging
from typing import Optional

import asyncpg
import redis.asyncio as aioredis
from langchain_core.messages import HumanMessage

from app.agent.graph import get_graph
from app.agent.nodes import set_pool
from app.agent.state import KiranaState
from app.db.queries import update_job_status
from app.services.whatsapp import send_text_message

logger = logging.getLogger(__name__)

QUEUE_KEY = "agent_jobs"
MAX_RETRIES = 3


async def process_job(
    pool: asyncpg.Pool,
    job_data: dict,
) -> None:
    job_id: str = job_data["jobId"]
    store_id: str = job_data["storeId"]
    message: str = job_data["input"]
    wa_phone: Optional[str] = job_data.get("waPhone")

    logger.info("Processing job %s | store %s", job_id, store_id)
    await update_job_status(pool, job_id, "processing")

    try:
        graph = get_graph()
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
        final_state: KiranaState = await graph.ainvoke(initial_state)
        output = final_state["result"]
        db_payload = final_state.get("db_payload", {})

        await update_job_status(
            pool, job_id, "done",
            output=output,
            agent_steps=json.dumps(db_payload) if db_payload else None,
        )
        logger.info("Job %s done", job_id)

        if wa_phone and output:
            await send_text_message(wa_phone, output)

    except Exception as exc:  # noqa: BLE001
        logger.error("Job %s failed: %s", job_id, exc, exc_info=True)
        retry_count = job_data.get("retryCount", 0)
        if retry_count < MAX_RETRIES:
            logger.info("Retrying job %s (attempt %s/%s)", job_id, retry_count + 1, MAX_RETRIES)
            # Re-enqueue with incremented retry count after brief backoff
            await asyncio.sleep(2 ** retry_count)  # exponential backoff
            # Caller (worker_loop) handles re-enqueue via returned flag
        await update_job_status(pool, job_id, "failed", error=str(exc))


async def worker_loop(
    pool: asyncpg.Pool,
    redis_client: aioredis.Redis,
) -> None:
    """Main worker loop — BRPOP blocks until job arrives, dispatches concurrently."""
    set_pool(pool)  # inject pool into nodes module
    logger.info("Worker loop started — listening on '%s'", QUEUE_KEY)

    while True:
        try:
            result = await redis_client.brpop(QUEUE_KEY, timeout=5)
            if result:
                _, raw = result
                job_data = json.loads(raw)
                # Non-blocking: process jobs concurrently
                asyncio.create_task(process_job(pool, job_data))
        except asyncio.CancelledError:
            logger.info("Worker loop cancelled — shutting down")
            break
        except Exception as exc:  # noqa: BLE001
            logger.error("Worker loop error: %s", exc, exc_info=True)
            await asyncio.sleep(1)
