"""
Greeting Agent

Fast, lightweight agent that handles greetings and basic interactions
without LLM calls. Delegates to reasoning agent when needed.
"""

import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlmodel import select

from app.database import get_session_context
from app.connections.models import ColumnMetadata, TableInsight


class GreetingAgentState(TypedDict):
    """State for the greeting agent workflow."""

    # Input
    question: str
    connection_id: int

    # Context
    db_info: dict | None  # Basic DB context (tables, summaries)

    # Routing
    is_greeting: bool
    needs_reasoning: bool  # Route to reasoning agent

    # Output
    response: str | None


# Greeting patterns (no LLM needed)
GREETING_PATTERNS = [
    r"^(hello|hi|hey|good\s*(morning|afternoon|evening)|greetings|howdy)[\s!?.]*$",
    r"^(what'?s?\s*up|yo|sup)[\s!?.]*$",
]

# Question patterns that need reasoning
QUESTION_PATTERNS = [
    r"\b(show|list|find|get|select|count|how\s+many|what|which|where|who)\b",
    r"\b(table|column|data|record|row|query)\b",
    r"\?$",
]


async def _get_db_info(connection_id: int) -> dict:
    """
    Get basic database info for greeting context.
    Returns table names and summaries without hitting external LLM.
    """
    async with get_session_context() as session:
        # Get table insights
        stmt = select(TableInsight).where(TableInsight.connection_id == connection_id)
        result = await session.execute(stmt)
        insights = result.scalars().all()

        tables = []
        for insight in insights:
            # Get column count
            col_stmt = select(ColumnMetadata).where(
                ColumnMetadata.table_insight_id == insight.id
            )
            col_result = await session.execute(col_stmt)
            columns = col_result.scalars().all()

            tables.append({
                "name": f"{insight.schema_name}.{insight.table_name}",
                "summary": insight.summary or "No description",
                "row_count": insight.row_count,
                "column_count": len(columns),
            })

        return {
            "table_count": len(tables),
            "tables": tables[:10],  # Limit for greeting context
        }


async def classify_intent_node(state: GreetingAgentState) -> GreetingAgentState:
    """
    Classify user intent using pattern matching (no LLM).
    Fast classification for greetings vs questions.
    """
    question = state["question"].strip().lower()

    # Check for greetings
    is_greeting = any(
        re.match(pattern, question, re.IGNORECASE)
        for pattern in GREETING_PATTERNS
    )

    # Check if it's a question needing reasoning
    needs_reasoning = any(
        re.search(pattern, question, re.IGNORECASE)
        for pattern in QUESTION_PATTERNS
    )

    # Short messages without question indicators are likely greetings
    if len(question.split()) <= 3 and not needs_reasoning:
        is_greeting = True

    state["is_greeting"] = is_greeting
    state["needs_reasoning"] = not is_greeting

    return state


async def load_db_context_node(state: GreetingAgentState) -> GreetingAgentState:
    """Load basic DB info for greeting context."""
    if state["is_greeting"]:
        try:
            state["db_info"] = await _get_db_info(state["connection_id"])
        except Exception:
            state["db_info"] = {"table_count": 0, "tables": []}

    return state


async def greeting_response_node(state: GreetingAgentState) -> GreetingAgentState:
    """Generate greeting response with DB context (no LLM)."""
    if not state["is_greeting"]:
        return state

    db_info = state.get("db_info") or {}
    table_count = db_info.get("table_count", 0)
    tables = db_info.get("tables", [])

    # Build greeting message
    greeting = "Hello! I'm your database assistant."

    if table_count > 0:
        greeting += f" I have access to **{table_count} table(s)**"

        # Add table summaries
        if tables:
            table_list = []
            for t in tables[:5]:  # Show up to 5 tables
                name = t["name"].split(".")[-1]  # Just table name
                rows = t.get("row_count", 0)
                table_list.append(f"- **{name}** ({rows:,} rows)")

            greeting += ":\n\n" + "\n".join(table_list)

            if table_count > 5:
                greeting += f"\n- ... and {table_count - 5} more"

        greeting += "\n\nHow can I help you query your data today?"
    else:
        greeting += " How can I help you today?"

    state["response"] = greeting
    return state


def route_from_classification(state: GreetingAgentState) -> str:
    """Route based on classification result."""
    if state["is_greeting"]:
        return "load_context"
    return "end"  # Will be handled by orchestrator


def create_greeting_agent() -> StateGraph:
    """Create the greeting agent workflow."""
    workflow = StateGraph(GreetingAgentState)

    # Add nodes
    workflow.add_node("classify", classify_intent_node)
    workflow.add_node("load_context", load_db_context_node)
    workflow.add_node("respond", greeting_response_node)

    # Define edges
    workflow.set_entry_point("classify")
    workflow.add_conditional_edges(
        "classify",
        route_from_classification,
        {
            "load_context": "load_context",
            "end": END,
        },
    )
    workflow.add_edge("load_context", "respond")
    workflow.add_edge("respond", END)

    return workflow.compile()


# Compiled greeting agent
greeting_agent = create_greeting_agent()


async def run_greeting_agent(
    question: str,
    connection_id: int,
) -> dict[str, Any]:
    """
    Run the greeting agent.

    Returns:
        Dict with:
        - needs_reasoning: bool - True if should delegate to reasoning agent
        - response: str | None - Greeting response if applicable
    """
    initial_state = GreetingAgentState(
        question=question,
        connection_id=connection_id,
        db_info=None,
        is_greeting=False,
        needs_reasoning=False,
        response=None,
    )

    final_state = await greeting_agent.ainvoke(initial_state)

    return {
        "needs_reasoning": final_state.get("needs_reasoning", True),
        "response": final_state.get("response"),
        "is_greeting": final_state.get("is_greeting", False),
    }
