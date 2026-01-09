"""
LangGraph Agent

Orchestrates between greeting agent and reasoning agent.

Workflow:
1. Greeting Agent - Fast pattern-based classification
2. If needs reasoning -> Reasoning Agent with full RAG workflow
"""

from typing import Any

from app.agent.greeting_agent import run_greeting_agent
from app.agent.reasoning_agent import run_reasoning_agent


async def run_agent(
    question: str,
    connection_id: int,
    explain_mode: bool = True,
) -> dict[str, Any]:
    """
    Run the agent to answer a database question.

    Uses a two-agent architecture:
    1. Greeting agent handles simple interactions (no LLM)
    2. Reasoning agent handles database questions (full RAG)

    Args:
        question: User's natural language question
        connection_id: Database connection ID
        explain_mode: If True, return SQL + explanation + data;
                     If False, return only raw CSV

    Returns:
        Dict with response, sql, explanation, data, etc.
    """
    # Step 1: Run greeting agent for fast classification
    greeting_result = await run_greeting_agent(
        question=question,
        connection_id=connection_id,
    )

    # If greeting was handled, return immediately (fast path)
    if greeting_result.get("is_greeting") and greeting_result.get("response"):
        return {
            "response": greeting_result["response"],
            "sql": None,
            "explanation": None,
            "data": None,
            "columns": None,
            "error": None,
        }

    # Step 2: Run reasoning agent for database questions
    reasoning_result = await run_reasoning_agent(
        question=question,
        connection_id=connection_id,
        explain_mode=explain_mode,
    )

    return reasoning_result
