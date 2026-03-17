"""LangGraph node implementations — one function per intent handler."""
import json
import logging
import re
import uuid
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage

from app.agent.llm import get_llm
from app.agent.state import KiranaState
from app.db import queries

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)

# Injected at worker startup — avoids passing pool through every node signature
_pool: "asyncpg.Pool | None" = None


def set_pool(pool: "asyncpg.Pool") -> None:
    global _pool
    _pool = pool


def _pool_required() -> "asyncpg.Pool":
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call set_pool() at startup")
    return _pool


def _strip_fences(text: str) -> str:
    """Strip markdown ```json ... ``` fences from LLM output."""
    return re.sub(r"```(?:json)?\n?", "", text).strip()


# ─── Intent Detection ────────────────────────────────────────────────────────

async def detect_intent(state: KiranaState) -> KiranaState:
    llm = get_llm()
    user_message = state["messages"][-1].content
    prompt = (
        "You are an AI assistant for a small Indian kirana (grocery) store.\n"
        "Classify the following message into exactly one intent:\n"
        "- inventory_update: adding/restocking/updating product quantity\n"
        "- khata_entry: udhaar, credit given, payment received, customer ledger\n"
        "- stock_query: asking about current stock level of a product\n"
        "- low_stock_alert: asking which items are running low or need reorder\n"
        "- unknown: anything else\n\n"
        f"Message: {user_message}\n\n"
        "Reply with only the intent label, nothing else."
    )
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    intent = response.content.strip().lower()
    valid = {"inventory_update", "khata_entry", "stock_query", "low_stock_alert"}
    intent = intent if intent in valid else "unknown"
    logger.info("[%s] Intent: %s", state["job_id"], intent)
    return {**state, "intent": intent}


# ─── Stock Query ─────────────────────────────────────────────────────────────

async def handle_stock_query(state: KiranaState) -> KiranaState:
    llm = get_llm()
    pool = _pool_required()
    user_message = state["messages"][-1].content

    extract_prompt = (
        "Extract the product name being asked about from this message.\n"
        "Return only the product name. If the user is asking about all products, return 'all'.\n"
        f"Message: {user_message}"
    )
    name_resp = await llm.ainvoke([HumanMessage(content=extract_prompt)])
    product_name = name_resp.content.strip()

    if product_name.lower() == "all":
        products = await queries.list_all_products(pool, state["store_id"])
        if not products:
            result = "No products found in your inventory."
        else:
            lines = [f"\u2022 {p['name']}: {p['current_stock']} {p['unit']}" for p in products]
            result = "Current stock:\n" + "\n".join(lines)
    else:
        prod = await queries.find_product_by_name(pool, state["store_id"], product_name)
        if prod:
            result = f"{prod['name']}: {prod['current_stock']} {prod['unit']} in stock."
            if float(prod["current_stock"]) <= float(prod["reorder_level"] or 0):
                result += " \u26a0\ufe0f Low stock \u2014 time to reorder."
        else:
            result = f"Product '{product_name}' not found. Check the name or add it first."

    return {**state, "result": result}


# ─── Low Stock Alert ─────────────────────────────────────────────────────────

async def handle_low_stock_alert(state: KiranaState) -> KiranaState:
    pool = _pool_required()
    items = await queries.list_low_stock_products(pool, state["store_id"])
    if not items:
        result = "\u2705 All items are above reorder level. Stock is healthy."
    else:
        lines = [
            f"\u2022 {i['name']}: {i['current_stock']}/{i['reorder_level']} {i['unit']}"
            for i in items
        ]
        result = f"\u26a0\ufe0f {len(items)} items need restocking:\n" + "\n".join(lines)
    return {**state, "result": result}


# ─── Inventory Update ────────────────────────────────────────────────────────

async def handle_inventory_update(state: KiranaState) -> KiranaState:
    llm = get_llm()
    pool = _pool_required()
    user_message = state["messages"][-1].content

    extract_prompt = (
        "Extract inventory update details from this message.\n"
        "Return valid JSON with fields:\n"
        '  product_name (string), quantity (number, always positive),\n'
        '  action ("add" to add to existing stock | "set" to set exact value)\n'
        "No explanation, only JSON.\n"
        f"Message: {user_message}"
    )
    response = await llm.ainvoke([HumanMessage(content=extract_prompt)])
    raw = _strip_fences(response.content)

    try:
        payload = json.loads(raw)
        product_name: str = payload["product_name"]
        quantity: float = float(payload["quantity"])
        action: str = payload.get("action", "add")
    except Exception:
        return {**state, "result": "Could not parse update. Try: 'Add 10 kg rice' or 'Set sugar to 25 kg'."}

    prod = await queries.find_product_by_name(pool, state["store_id"], product_name)
    if not prod:
        return {**state, "result": f"Product '{product_name}' not found. Add it via the dashboard first."}

    current = float(prod["current_stock"])
    new_stock = round((current + quantity) if action == "add" else quantity, 3)

    db_payload = {
        "type": "inventory_update",
        "product_id": prod["id"],
        "product_name": prod["name"],
        "old_stock": current,
        "new_stock": new_stock,
        "action": action,
        "quantity": quantity,
    }
    verb = "increased by" if action == "add" else "set to"
    result = (
        f"\U0001f4e6 Staged: {prod['name']} stock {verb} "
        f"{quantity if action == 'add' else new_stock} {prod['unit']}.\n"
        f"New total would be {new_stock} {prod['unit']}.\n"
        f"Reply 'confirm' to apply, or 'cancel' to discard."
    )
    return {**state, "result": result, "confirmed": False, "db_payload": db_payload}


# ─── Khata Entry ─────────────────────────────────────────────────────────────

async def handle_khata_entry(state: KiranaState) -> KiranaState:
    llm = get_llm()
    pool = _pool_required()
    user_message = state["messages"][-1].content

    extract_prompt = (
        "Extract khata (credit ledger) entry details from this message.\n"
        "Return valid JSON with fields:\n"
        "  customer_name (string),\n"
        "  amount (number: positive = udhaar/credit given, negative = payment received),\n"
        "  note (string, brief)\n"
        "No explanation, only JSON.\n"
        f"Message: {user_message}"
    )
    response = await llm.ainvoke([HumanMessage(content=extract_prompt)])
    raw = _strip_fences(response.content)

    try:
        payload = json.loads(raw)
        customer_name: str = payload["customer_name"]
        amount: float = float(payload["amount"])
        note: str = payload.get("note", "")
    except Exception:
        return {**state, "result": "Could not parse. Try: 'Ramesh ne 200 ka maal liya' or 'Sunita ne 500 diye'."}

    cust = await queries.find_customer_by_name(pool, state["store_id"], customer_name)
    if not cust:
        return {**state, "result": f"Customer '{customer_name}' not found. Add them first via the dashboard."}

    entry_id = str(uuid.uuid4())
    await queries.insert_staged_khata_entry(
        pool, entry_id, state["store_id"], cust["id"], str(amount), note
    )

    direction = "udhaar (credit given)" if amount > 0 else "payment received"
    result = (
        f"\U0001f4d2 Staged: {cust['name']} \u2014 \u20b9{abs(amount)} {direction}.\n"
        f"Note: {note}\n"
        f"Confirm via dashboard to apply to ledger. (Entry ID: {entry_id})"
    )
    db_payload = {"type": "khata_entry", "entry_id": entry_id, "customer_id": cust["id"]}
    return {**state, "result": result, "confirmed": False, "db_payload": db_payload}


# ─── Unknown ─────────────────────────────────────────────────────────────────

async def handle_unknown(state: KiranaState) -> KiranaState:
    result = (
        "Sorry, I didn't understand that.\n"
        "You can ask me to:\n"
        "\u2022 Check stock: 'Kitna chawal bacha hai?'\n"
        "\u2022 Update stock: 'Add 10 kg sugar'\n"
        "\u2022 Khata: 'Ramesh ne 200 ka maal liya'\n"
        "\u2022 Low stock: 'Kya khatam ho raha hai?'"
    )
    return {**state, "result": result}
