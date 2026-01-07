"""
LangGraph Agent

Multi-step agent for querying databases using natural language.

Workflow:
1. Understand - Parse user intent
2. Retrieve - Search for relevant tables/columns
3. Generate - Write SQL and synthesize answer
"""

import json
import re
from typing import Any, TypedDict

import ollama
from ollama import Client
from langgraph.graph import END, StateGraph

from app.config import get_settings
from app.rag.tools import execute_sql_query, search_database_data, rows_to_csv

settings = get_settings()


class AgentState(TypedDict):
    """State for the agent workflow."""

    # Input
    question: str
    connection_id: int
    explain_mode: bool

    # Intermediate
    intent: str | None
    relevant_tables: list[dict] | None
    generated_sql: str | None

    # Output
    response: str | None
    sql_query: str | None
    explanation: str | None
    data: list[list] | None
    columns: list[str] | None
    error: str | None


async def understand_node(state: AgentState) -> AgentState:
    """
    Parse user intent from the question.

    Determines what kind of data the user is looking for.
    """
    question = state["question"]

    prompt = f"""Analyze this database question and extract the key intent.

Question: {question}

Identify:
1. What data is being requested?
2. Any filters or conditions mentioned?
3. Any aggregations (count, sum, average)?
4. Any sorting or limiting requirements?

Respond with a brief intent summary (1-2 sentences).
If the question is a greeting (like "Hello", "Hi") or a generic polite phrase, just summarize it as such.
"""

    # Create client with configured URL
    client = Client(host=settings.ollama_base_url)

    try:
        response = client.chat(
            model=settings.ollama_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 200},
        )

        content = response["message"]["content"]

        # Handle /think tags from qwen3
        # Remove thinking content if present
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        # Check for greetings
        greetings = ["hello", "hi", "good morning", "good afternoon", "good evening", "hey"]
        is_greeting = any(g in question.lower() for g in greetings)
        
        if is_greeting and len(question.split()) <= 3:
            state["intent"] = "GREETING"
            state["response"] = "Hello! I am your database assistant. How can I help you query your data today?"
        else:
            state["intent"] = content

    except Exception as e:
        state["intent"] = f"Find data related to: {question}"
        state["error"] = f"Intent parsing warning: {str(e)[:100]}"

    return state


async def retrieve_node(state: AgentState) -> AgentState:
    """
    Retrieve relevant tables and columns from vector store.
    """
    question = state["question"]
    connection_id = state["connection_id"]
    intent = state.get("intent", question)

    # Search for relevant tables
    search_query = f"{question} {intent}"
    results_json = await search_database_data(
        query=search_query,
        connection_id=connection_id,
        limit=5,
    )

    results = json.loads(results_json)

    if results["status"] == "success" and results["results"]:
        state["relevant_tables"] = results["results"]
    else:
        state["relevant_tables"] = []
        if not state.get("error"):
            state["error"] = "No relevant tables found"

    return state


async def generate_node(state: AgentState) -> AgentState:
    """
    Generate SQL query and execute it.
    """
    question = state["question"]
    connection_id = state["connection_id"]
    explain_mode = state["explain_mode"]
    relevant_tables = state.get("relevant_tables", [])

    if state.get("intent") == "GREETING" and state.get("response"):
        return state

    if not relevant_tables:
        state["response"] = "I couldn't find any relevant tables for your question."
        state["error"] = "No tables to query"
        return state

    # Build context from relevant tables
    context_parts = []
    for table in relevant_tables:
        doc = table.get("document", "")
        if doc:
            context_parts.append(f"--- Table: {table['table_name']} ---\n{doc[:2000]}")

    context = "\n\n".join(context_parts)

    # Generate SQL
    sql_prompt = f"""You are a PostgreSQL expert. Generate a SINGLE SQL query to answer this question.

Question: {question}

Available tables and their schemas:
{context}

Rules:
1. Use only the tables and columns shown above
2. Use proper PostgreSQL syntax
3. Limit results to 100 rows unless specifically asked for more
4. Use double quotes for column/table names if they have special characters
5. Return ONLY ONE SQL query - no multiple statements
6. Do NOT include multiple queries separated by semicolons
7. If you need to combine data, use JOINs, subqueries, or CTEs in a single statement
8. No explanation, just the query

SQL:
"""

    # Create client with configured URL
    client = Client(host=settings.ollama_base_url)

    try:
        response = client.chat(
            model=settings.ollama_model,
            messages=[{"role": "user", "content": sql_prompt}],
            options={"temperature": 0.1, "num_predict": 500},
        )

        content = response["message"]["content"]

        # Remove thinking content if present
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        # Extract SQL from response
        sql = extract_sql(content)

        if not sql:
            state["error"] = "Could not generate valid SQL"
            state["response"] = "I couldn't generate a valid SQL query for your question."
            return state

        state["generated_sql"] = sql
        state["sql_query"] = sql

        # Execute SQL
        result = await execute_sql_query(sql, connection_id)

        if result["status"] == "error":
            state["error"] = result["message"]
            state["response"] = f"Query execution failed: {result['message']}"
            return state

        state["columns"] = result["columns"]
        state["data"] = result["rows"]

        # Generate response based on mode
        if explain_mode:
            # Generate explanation
            explanation = await generate_explanation(
                question, sql, result["columns"], result["rows"][:10]
            )
            state["explanation"] = explanation
            state["response"] = json.dumps({
                "sql": sql,
                "explanation": explanation,
                "data": result["rows"],
                "columns": result["columns"],
                "row_count": result["row_count"],
            })
        else:
            # Raw CSV output
            csv_output = rows_to_csv(result["columns"], result["rows"])
            state["response"] = csv_output

    except Exception as e:
        state["error"] = str(e)
        state["response"] = f"Error generating response: {str(e)}"

    return state


def extract_sql(text: str) -> str | None:
    """Extract SQL query from LLM response. Only returns the first statement if multiple exist."""
    sql = None
    
    # Try to find SQL in code blocks
    code_block_match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        sql = code_block_match.group(1).strip()
    else:
        # Try to find SELECT statement
        select_match = re.search(
            r"(SELECT\s+.*?(?:;|$))",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if select_match:
            sql = select_match.group(1).strip()
        elif text.strip().upper().startswith("SELECT"):
            sql = text.strip()
    
    if not sql:
        return None
    
    # Handle multiple statements - only take the first one
    # Split by semicolons followed by whitespace and a new statement keyword
    # This is tricky because semicolons can appear inside strings
    # Simple approach: split by semicolon followed by newline and SELECT/WITH/INSERT/UPDATE/DELETE
    multi_stmt_pattern = r";\s*(?=\n\s*(?:SELECT|WITH|INSERT|UPDATE|DELETE))"
    statements = re.split(multi_stmt_pattern, sql, flags=re.IGNORECASE)
    
    if statements:
        sql = statements[0].strip()
    
    # Remove trailing semicolon
    if sql.endswith(";"):
        sql = sql[:-1]
    
    return sql


async def generate_explanation(
    question: str, sql: str, columns: list[str], sample_rows: list[list]
) -> str:
    """Generate a natural language explanation of the results."""
    sample_str = json.dumps(sample_rows[:5], default=str)

    prompt = f"""Briefly explain these SQL query results.

Question: {question}
SQL: {sql}
Columns: {columns}
Sample data: {sample_str}

Give a 1-2 sentence summary of what the data shows. Be concise.
"""

    # Create client with configured URL
    client = Client(host=settings.ollama_base_url)

    try:
        response = client.chat(
            model=settings.ollama_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3, "num_predict": 150},
        )

        content = response["message"]["content"]
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content

    except Exception:
        return "Query executed successfully."


def create_agent_graph() -> StateGraph:
    """Create the LangGraph agent workflow."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("understand", understand_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("generate", generate_node)

    # Define edges
    workflow.set_entry_point("understand")
    workflow.add_edge("understand", "retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)

    return workflow.compile()


# Compiled agent
agent = create_agent_graph()


async def run_agent(
    question: str,
    connection_id: int,
    explain_mode: bool = True,
) -> dict[str, Any]:
    """
    Run the agent to answer a database question.

    Args:
        question: User's natural language question
        connection_id: Database connection ID
        explain_mode: If True, return SQL + explanation + data;
                     If False, return only raw CSV

    Returns:
        Dict with response, sql, explanation, data, etc.
    """
    initial_state = AgentState(
        question=question,
        connection_id=connection_id,
        explain_mode=explain_mode,
        intent=None,
        relevant_tables=None,
        generated_sql=None,
        response=None,
        sql_query=None,
        explanation=None,
        data=None,
        columns=None,
        error=None,
    )

    # Run the agent
    final_state = await agent.ainvoke(initial_state)

    return {
        "response": final_state.get("response"),
        "sql": final_state.get("sql_query"),
        "explanation": final_state.get("explanation"),
        "data": final_state.get("data"),
        "columns": final_state.get("columns"),
        "error": final_state.get("error"),
    }
