"""Unit tests for LangGraph nodes — mock LLM and DB, test logic only."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.state import KiranaState
from app.agent.nodes import (
    detect_intent,
    handle_stock_query,
    handle_low_stock_alert,
    handle_inventory_update,
    handle_khata_entry,
    handle_unknown,
    set_pool,
)
from langchain_core.messages import HumanMessage, AIMessage


BASE_STATE: KiranaState = {
    "messages": [HumanMessage(content="test")],
    "job_id": "test-job-1",
    "store_id": "store-abc",
    "intent": "",
    "confirmed": False,
    "result": "",
    "db_payload": {},
    "wa_phone": None,
}


# ─── Intent Detection ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_detect_intent_stock_query():
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content="stock_query")
    with patch("app.agent.nodes.get_llm", return_value=mock_llm):
        state = {**BASE_STATE, "messages": [HumanMessage(content="Kitna chawal bacha hai?")]}
        result = await detect_intent(state)
    assert result["intent"] == "stock_query"


@pytest.mark.asyncio
async def test_detect_intent_unknown_fallback():
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content="garbage_output")
    with patch("app.agent.nodes.get_llm", return_value=mock_llm):
        result = await detect_intent(BASE_STATE)
    assert result["intent"] == "unknown"


# ─── Stock Query ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_stock_query_found():
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content="rice")
    mock_pool = AsyncMock()

    fake_product = {
        "id": "p1", "name": "Rice", "current_stock": "50",
        "unit": "kg", "selling_price": "40", "reorder_level": "10",
        "name_aliases": "chawal",
    }
    with patch("app.agent.nodes.get_llm", return_value=mock_llm), \
         patch("app.agent.nodes.queries.find_product_by_name", return_value=fake_product), \
         patch("app.agent.nodes._pool_required", return_value=mock_pool):
        result = await handle_stock_query(BASE_STATE)
    assert "Rice" in result["result"]
    assert "50" in result["result"]


@pytest.mark.asyncio
async def test_handle_stock_query_not_found():
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content="xyz_unknown")
    mock_pool = AsyncMock()
    with patch("app.agent.nodes.get_llm", return_value=mock_llm), \
         patch("app.agent.nodes.queries.find_product_by_name", return_value=None), \
         patch("app.agent.nodes._pool_required", return_value=mock_pool):
        result = await handle_stock_query(BASE_STATE)
    assert "not found" in result["result"]


# ─── Low Stock Alert ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_low_stock_alert_items_found():
    mock_pool = AsyncMock()
    low_items = [
        {"name": "Sugar", "current_stock": "2", "unit": "kg", "reorder_level": "5"},
    ]
    with patch("app.agent.nodes.queries.list_low_stock_products", return_value=low_items), \
         patch("app.agent.nodes._pool_required", return_value=mock_pool):
        result = await handle_low_stock_alert(BASE_STATE)
    assert "Sugar" in result["result"]
    assert "restock" in result["result"]


@pytest.mark.asyncio
async def test_handle_low_stock_alert_all_healthy():
    mock_pool = AsyncMock()
    with patch("app.agent.nodes.queries.list_low_stock_products", return_value=[]), \
         patch("app.agent.nodes._pool_required", return_value=mock_pool):
        result = await handle_low_stock_alert(BASE_STATE)
    assert "healthy" in result["result"]


# ─── Inventory Update ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_inventory_update_success():
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(
        content=json.dumps({"product_name": "Rice", "quantity": 10, "action": "add"})
    )
    mock_pool = AsyncMock()
    fake_product = {
        "id": "p1", "name": "Rice", "current_stock": "50",
        "unit": "kg", "selling_price": "40", "reorder_level": "10",
        "name_aliases": None,
    }
    with patch("app.agent.nodes.get_llm", return_value=mock_llm), \
         patch("app.agent.nodes.queries.find_product_by_name", return_value=fake_product), \
         patch("app.agent.nodes._pool_required", return_value=mock_pool):
        result = await handle_inventory_update(BASE_STATE)
    assert result["db_payload"]["type"] == "inventory_update"
    assert result["db_payload"]["new_stock"] == 60.0
    assert result["confirmed"] is False


@pytest.mark.asyncio
async def test_handle_inventory_update_bad_json():
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content="not json at all")
    mock_pool = AsyncMock()
    with patch("app.agent.nodes.get_llm", return_value=mock_llm), \
         patch("app.agent.nodes._pool_required", return_value=mock_pool):
        result = await handle_inventory_update(BASE_STATE)
    assert "Could not parse" in result["result"]


# ─── Unknown ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_unknown():
    result = await handle_unknown(BASE_STATE)
    assert "didn't understand" in result["result"]
