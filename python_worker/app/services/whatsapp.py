"""WhatsApp Meta Cloud API v19.0 — outbound message delivery."""
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

WA_API_URL = "https://graph.facebook.com/v19.0/{phone_id}/messages"


async def send_text_message(to_phone: str, message: str) -> None:
    """
    Send a WhatsApp text message to `to_phone` (E.164 format, e.g. '919876543210').
    Silently skips if WA credentials are not configured.
    """
    if not settings.WA_PHONE_NUMBER_ID or not settings.WA_ACCESS_TOKEN:
        logger.warning("WhatsApp credentials not set — skipping outbound reply to %s", to_phone)
        return

    url = WA_API_URL.format(phone_id=settings.WA_PHONE_NUMBER_ID)
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": message},
    }
    headers = {
        "Authorization": f"Bearer {settings.WA_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 200:
            logger.info("WhatsApp reply sent to %s", to_phone)
        else:
            logger.error("WhatsApp send failed [%s]: %s", resp.status_code, resp.text)
