"""Unit tests for WhatsApp service."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.whatsapp import send_text_message


@pytest.mark.asyncio
async def test_send_message_skips_when_no_credentials():
    with patch("app.services.whatsapp.settings") as mock_settings:
        mock_settings.WA_PHONE_NUMBER_ID = ""
        mock_settings.WA_ACCESS_TOKEN = ""
        # Should not raise, should log warning and return
        await send_text_message("919876543210", "Hello")


@pytest.mark.asyncio
async def test_send_message_calls_meta_api():
    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.services.whatsapp.settings") as mock_settings, \
         patch("app.services.whatsapp.httpx.AsyncClient", return_value=mock_client):
        mock_settings.WA_PHONE_NUMBER_ID = "123456"
        mock_settings.WA_ACCESS_TOKEN = "token_abc"
        await send_text_message("919876543210", "Test message")

    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert "919876543210" in str(call_kwargs)
