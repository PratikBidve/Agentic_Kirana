"""LangGraph graph assembly — wires nodes and edges."""
from functools import lru_cache

from langgraph.graph import StateGraph, END

from app.agent.state import KiranaState
from app.agent.nodes import (
    detect_intent,
    handle_stock_query,
    handle_low_stock_alert,
    handle_inventory_update,
    handle_khata_entry,
    handle_unknown,
)


def _route_by_intent(state: KiranaState) -> str:
    return state.get("intent", "unknown")


@lru_cache
def get_graph():
    """Build and compile the graph once — reused across all jobs."""
    g = StateGraph(KiranaState)

    g.add_node("detect_intent", detect_intent)
    g.add_node("stock_query", handle_stock_query)
    g.add_node("low_stock_alert", handle_low_stock_alert)
    g.add_node("inventory_update", handle_inventory_update)
    g.add_node("khata_entry", handle_khata_entry)
    g.add_node("unknown", handle_unknown)

    g.set_entry_point("detect_intent")
    g.add_conditional_edges(
        "detect_intent",
        _route_by_intent,
        {
            "stock_query": "stock_query",
            "low_stock_alert": "low_stock_alert",
            "inventory_update": "inventory_update",
            "khata_entry": "khata_entry",
            "unknown": "unknown",
        },
    )
    for node in ["stock_query", "low_stock_alert", "inventory_update", "khata_entry", "unknown"]:
        g.add_edge(node, END)

    return g.compile()
