from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from satmi_agent.config import settings
from satmi_agent.nodes import (
    classify_intent,
    compose_response,
    execute_action,
    handoff_to_human_node,
    input_guardrails,
    policy_guard,
    retrieve_policy_node,
    should_handoff,
)
from satmi_agent.state import AgentState


def _build_checkpointer():
    if settings.database_url.startswith("postgresql"):
        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            conn_string = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
            checkpointer = PostgresSaver.from_conn_string(conn_string)
            checkpointer.setup()
            return checkpointer
        except Exception:
            return InMemorySaver()

    return InMemorySaver()


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("classify_intent", classify_intent)
    graph.add_node("input_guardrails", input_guardrails)
    graph.add_node("policy_guard", policy_guard)
    graph.add_node("retrieve_policy", retrieve_policy_node)
    graph.add_node("execute_action", execute_action)
    graph.add_node("compose_response", compose_response)
    graph.add_node("handoff_to_human", handoff_to_human_node)

    graph.add_edge(START, "input_guardrails")
    graph.add_edge("input_guardrails", "classify_intent")
    graph.add_edge("classify_intent", "policy_guard")
    graph.add_edge("policy_guard", "retrieve_policy")
    graph.add_edge("retrieve_policy", "execute_action")

    graph.add_conditional_edges(
        "execute_action",
        should_handoff,
        {
            "respond": "compose_response",
            "handoff": "handoff_to_human",
        },
    )

    graph.add_edge("compose_response", END)
    graph.add_edge("handoff_to_human", END)

    return graph.compile(checkpointer=_build_checkpointer())


compiled_graph = build_graph()
