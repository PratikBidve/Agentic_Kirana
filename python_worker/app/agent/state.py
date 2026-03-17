"""LangGraph state definition."""
from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class KiranaState(TypedDict):
    messages: Annotated[list, add_messages]
    job_id: str
    store_id: str
    intent: str           # inventory_update | khata_entry | stock_query | low_stock_alert | unknown
    confirmed: bool       # human-in-the-loop flag
    result: str           # final natural-language response
    db_payload: dict      # structured payload for DB confirm step
    wa_phone: Optional[str]  # E.164 phone for WhatsApp reply routing
