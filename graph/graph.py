import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.graph import END, START, StateGraph

from graph import state
from graph.nodes import (
    cond_tools,
    finalize_node,
    general_node,
    route_decision,
    router_node,
    tools_node,
    tools_validation,
)


def build_graph(checkpointer=None, store=None):
    """
    router → general → END
           → tools_node → tools_validation ⟲ (حداکثر تلاش) → finalize → END

    checkpointer: ماندگاری پیام‌های هر thread (بعد از refresh)
    store       : حافظه‌ی بلندمدت یادگیرنده (router_node آن را می‌گیرد)
    """
    builder = StateGraph(state.Graph_state)

    builder.add_node("router", router_node)
    builder.add_node("general", general_node)
    builder.add_node("tools_node", tools_node)
    builder.add_node("tools_validation", tools_validation)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router", route_decision, {"tools": "tools_node", "general": "general"}
    )
    builder.add_edge("tools_node", "tools_validation")
    builder.add_conditional_edges(
        "tools_validation", cond_tools, {"end": "finalize", "tools_node": "tools_node"}
    )
    builder.add_edge("general", END)
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer, store=store)