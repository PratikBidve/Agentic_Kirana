"""FastAPI route definitions — health check + WhatsApp webhook."""
import json
import logging
import uuid

from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.db.queries import find_store_by_phone, insert_agent_job

logger = logging.getLogger(__name__)
router = APIRouter()

QUEUE_KEY = "agent_jobs"


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "2.0.0"}


@router.get("/webhook/whatsapp")
async def whatsapp_verify(request: Request) -> Response:
    """
    Meta webhook verification handshake.
    Called once when you register the webhook in Meta App Dashboard.
    """
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == settings.WA_VERIFY_TOKEN
    ):
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    return Response(status_code=403)


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request) -> dict:
    """
    Inbound WhatsApp message handler.
    Looks up store by phone number, creates agent_job, enqueues to Redis.
    Always returns 200 — Meta retries aggressively on non-200.
    """
    body = await request.json()
    pool = request.app.state.pg_pool
    redis_client = request.app.state.redis_client

    try:
        entry = body["entry"][0]
        change = entry["changes"][0]["value"]
        messages = change.get("messages", [])

        if not messages:
            return {"status": "no_message"}  # delivery receipt / status update

        msg = messages[0]
        wa_phone: str = msg["from"]  # E.164, e.g. "919876543210"
        text: str = msg.get("text", {}).get("body", "").strip()

        if not text:
            return {"status": "non_text_ignored"}

        store = await find_store_by_phone(pool, wa_phone)
        if not store:
            logger.warning("Unregistered WA number: %s", wa_phone)
            return {"status": "store_not_found"}

        job_id = str(uuid.uuid4())
        await insert_agent_job(pool, job_id, store["id"], text)

        payload = json.dumps({
            "jobId": job_id,
            "storeId": store["id"],
            "input": text,
            "waPhone": wa_phone,
        })
        await redis_client.lpush(QUEUE_KEY, payload)
        logger.info("WA job %s enqueued for store %s", job_id, store["id"])
        return {"status": "queued", "job_id": job_id}

    except Exception as exc:  # noqa: BLE001
        logger.error("Webhook error: %s", exc, exc_info=True)
        return {"status": "error"}  # always 200 to Meta
