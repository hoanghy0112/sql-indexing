"""
LangGraph Agent

Multi-step agent for querying databases using natural language.

Workflow:
1. Understand - Parse user intent and extract searchable terms
2. Retrieve - Search for relevant tables/columns
3. Enrich - Get detailed table insights with column metadata
4. Search Values - Resolve user terms to actual data values
5. Generate - Write SQL with retry on errors and synthesize answer
"""

import json
import re
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph

from app.config import get_settings
from app.rag.tools import (
    execute_sql_query,
    get_table_insights,
    rows_to_csv,
    search_by_index,
    search_database_data,
)

settings = get_settings()

# Initialize LLM clients with different settings
llm_intent = ChatOllama(
    model=settings.ollama_model,
    base_url=settings.ollama_base_url,
    temperature=0.1,
    num_predict=300,
)

llm_sql = ChatOllama(
    model=settings.ollama_model,
    base_url=settings.ollama_base_url,
    temperature=0.1,
    num_predict=500,
)

llm_explain = ChatOllama(
    model=settings.ollama_model,
    base_url=settings.ollama_base_url,
    temperature=0.3,
    num_predict=150,
)

# Maximum SQL retry attempts on syntax errors
MAX_SQL_RETRIES = 3


class AgentState(TypedDict):
    """State for the agent workflow."""

    # Input
    question: str
    connection_id: int
    explain_mode: bool

    # Intermediate
    intent: str | None
    searchable_terms: list[dict] | None  # Terms to search for in indexes
    relevant_tables: list[dict] | None
    table_insights: list[dict] | None  # Detailed table/column metadata
    resolved_values: dict | None  # Mapping of user terms to actual values
    generated_sql: str | None
    sql_attempts: int  # Number of SQL generation attempts
    last_sql_error: str | None  # Last SQL error for retry context

    # Output
    response: str | None
    sql_query: str | None
    explanation: str | None
    data: list[list] | None
    columns: list[str] | None
    error: str | None


async def understand_node(state: AgentState) -> AgentState:
    """
    Parse user intent from the question and extract searchable terms.

    Determines what kind of data the user is looking for and identifies
    terms that might need to be resolved to actual database values.
    """
    question = state["question"]

    prompt = f"""Analyze this database question and extract key information.

Question: {question}

Provide a JSON response with:
1. "intent": Brief summary of what data is being requested (1-2 sentences)
2. "searchable_terms": List of values/terms the user mentions that might need to be looked up in the database
   (e.g., city names, product names, statuses, categories - NOT column names or table names)
   Each term should have: "term" (the value), "likely_column_type" (city, name, status, category, etc.)

Example for "Show me orders from New York with status pending":
{{
  "intent": "Find orders filtered by city and status",
  "searchable_terms": [
    {{"term": "New York", "likely_column_type": "city"}},
    {{"term": "pending", "likely_column_type": "status"}}
  ]
}}

For greetings like "Hello", respond with:
{{
  "intent": "GREETING",
  "searchable_terms": []
}}

Respond ONLY with valid JSON, no other text.
"""

    try:
        response = llm_intent.invoke([HumanMessage(content=prompt)])
        content = response.content
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        # Try to parse JSON
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
            if json_match:
                content = json_match.group(1).strip()

            parsed = json.loads(content)
            state["intent"] = parsed.get("intent", f"Find data related to: {question}")
            state["searchable_terms"] = parsed.get("searchable_terms", [])

            # Handle greetings
            if state["intent"] == "GREETING":
                state["response"] = "Hello! I am your database assistant. How can I help you query your data today?"

        except json.JSONDecodeError:
            # Fallback: check for greetings manually
            greetings = ["hello", "hi", "good morning", "good afternoon", "good evening", "hey"]
            is_greeting = any(g in question.lower() for g in greetings)

            if is_greeting and len(question.split()) <= 3:
                state["intent"] = "GREETING"
                state["searchable_terms"] = []
                state["response"] = "Hello! I am your database assistant. How can I help you query your data today?"
            else:
                state["intent"] = f"Find data related to: {question}"
                state["searchable_terms"] = []

    except Exception as e:
        state["intent"] = f"Find data related to: {question}"
        state["searchable_terms"] = []
        state["error"] = f"Intent parsing warning: {str(e)[:100]}"

    return state


async def retrieve_node(state: AgentState) -> AgentState:
    """
    Retrieve relevant tables and columns from vector store.
    """
    question = state["question"]
    connection_id = state["connection_id"]
    intent = state.get("intent", question)

    # Skip if greeting
    if intent == "GREETING":
        return state

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


async def enrich_node(state: AgentState) -> AgentState:
    """
    Get detailed table insights including column metadata, categorical values, etc.
    """
    if state.get("intent") == "GREETING":
        return state

    relevant_tables = state.get("relevant_tables", [])
    if not relevant_tables:
        return state

    connection_id = state["connection_id"]
    table_names = [t["table_name"] for t in relevant_tables]

    # Get detailed insights
    insights_json = await get_table_insights(
        connection_id=connection_id,
        table_names=table_names,
    )

    insights = json.loads(insights_json)

    if insights["status"] == "success":
        state["table_insights"] = insights["tables"]
    else:
        state["table_insights"] = []

    return state


async def search_values_node(state: AgentState) -> AgentState:
    """
    Search for actual data values that match user's search terms.
    This resolves synonyms and abbreviations to exact database values.
    """
    if state.get("intent") == "GREETING":
        return state

    searchable_terms = state.get("searchable_terms", [])
    table_insights = state.get("table_insights", [])
    connection_id = state["connection_id"]

    if not searchable_terms or not table_insights:
        state["resolved_values"] = {}
        return state

    resolved = {}

    for term_info in searchable_terms:
        term = term_info.get("term", "")
        likely_type = term_info.get("likely_column_type", "").lower()

        if not term:
            continue

        # Try to find matching columns based on likely type
        for table in table_insights:
            for column in table.get("columns", []):
                col_name = column.get("column_name", "").lower()
                col_summary = (column.get("column_summary") or "").lower()

                # Check if column is likely to contain this type of data
                type_matches = (
                    likely_type in col_name or
                    likely_type in col_summary or
                    (likely_type == "city" and any(x in col_name for x in ["city", "location", "address"])) or
                    (likely_type == "status" and "status" in col_name) or
                    (likely_type == "category" and any(x in col_name for x in ["category", "type", "kind"])) or
                    (likely_type == "name" and "name" in col_name)
                )

                # Also check if column has categorical values (more likely to need resolution)
                has_categorical = column.get("indexing_strategy") == "categorical"

                if type_matches or has_categorical:
                    # Try to search for the value
                    search_result_json = await search_by_index(
                        connection_id=connection_id,
                        table_name=table["table_name"],
                        column_name=column["column_name"],
                        search_term=term,
                    )

                    search_result = json.loads(search_result_json)

                    if search_result["status"] == "success" and search_result["matches"]:
                        # Store the best match
                        best_match = search_result["matches"][0]
                        key = f"{table['table_name']}.{column['column_name']}"
                        resolved[key] = {
                            "original_term": term,
                            "actual_value": best_match["value"],
                            "match_type": best_match["match_type"],
                            "score": best_match["score"],
                        }
                        break  # Found a match for this term

            if term in str(resolved.values()):
                break  # Already resolved this term

    state["resolved_values"] = resolved
    return state


async def generate_node(state: AgentState) -> AgentState:
    """
    Generate SQL query with retry logic and execute it.
    """
    question = state["question"]
    connection_id = state["connection_id"]
    explain_mode = state["explain_mode"]
    relevant_tables = state.get("relevant_tables", [])
    table_insights = state.get("table_insights", [])
    resolved_values = state.get("resolved_values", {})
    sql_attempts = state.get("sql_attempts", 0)
    last_sql_error = state.get("last_sql_error")

    if state.get("intent") == "GREETING" and state.get("response"):
        return state

    if not relevant_tables:
        state["response"] = "I couldn't find any relevant tables for your question."
        state["error"] = "No tables to query"
        return state

    # Build enhanced context from table insights (preferred) or relevant tables
    context_parts = []

    if table_insights:
        for table in table_insights:
            table_context = f"--- Table: {table['schema_name']}.{table['table_name']} ---\n"
            table_context += f"Summary: {table.get('summary', 'No summary')}\n"
            table_context += f"Row count: {table.get('row_count', 'unknown')}\n\n"
            table_context += "Columns:\n"

            for col in table.get("columns", []):
                col_line = f"  - {col['column_name']} ({col['data_type']})"
                if col.get("is_primary_key"):
                    col_line += " [PRIMARY KEY]"
                if col.get("is_foreign_key"):
                    col_line += f" [FK -> {col.get('foreign_key_ref', 'unknown')}]"

                # Add categorical values if available
                if col.get("categorical_values"):
                    values = col["categorical_values"][:10]  # Limit to 10
                    col_line += f"\n    Possible values: {values}"

                if col.get("column_summary"):
                    col_line += f"\n    Description: {col['column_summary'][:100]}"

                table_context += col_line + "\n"

            context_parts.append(table_context)
    else:
        # Fallback to basic relevant_tables info
        for table in relevant_tables:
            doc = table.get("document", "")
            if doc:
                context_parts.append(f"--- Table: {table['table_name']} ---\n{doc[:2000]}")

    context = "\n\n".join(context_parts)

    # Add resolved values context
    value_hints = ""
    if resolved_values:
        hints = []
        for key, info in resolved_values.items():
            hints.append(
                f"  - For '{info['original_term']}' in {key}, use exact value: '{info['actual_value']}'"
            )
        value_hints = "\n\nIMPORTANT - Use these exact values:\n" + "\n".join(hints)

    # Add retry context if this is a retry
    retry_context = ""
    if sql_attempts > 0 and last_sql_error:
        retry_context = f"""
PREVIOUS ATTEMPT FAILED with error: {last_sql_error}

Please fix the SQL based on this error. Common fixes:
- Check column names match exactly (case-sensitive)
- Check table names are correct
- Ensure proper quoting of identifiers with special characters
- Check data types match the operation (e.g., no string operations on numbers)
"""

    # Generate SQL
    sql_prompt = f"""You are a PostgreSQL expert. Generate a SINGLE SQL query to answer this question.

Question: {question}

Available tables and their schemas:
{context}
{value_hints}
{retry_context}
Rules:
1. Use only the tables and columns shown above
2. Use proper PostgreSQL syntax
3. Limit results to 100 rows unless specifically asked for more
4. Use double quotes for column/table names if they have special characters
5. Return ONLY ONE SQL query - no multiple statements
6. Do NOT include multiple queries separated by semicolons
7. If you need to combine data, use JOINs, subqueries, or CTEs in a single statement
8. When filtering by values, use the EXACT values specified in the "Use these exact values" section above
9. No explanation, just the query

SQL:
"""

    try:
        response = llm_sql.invoke([HumanMessage(content=sql_prompt)])
        content = response.content
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
            # Check if we should retry
            error_msg = result["message"]
            is_syntax_error = "syntax" in error_msg.lower() or "column" in error_msg.lower() or "relation" in error_msg.lower()

            if is_syntax_error and sql_attempts < MAX_SQL_RETRIES - 1:
                state["sql_attempts"] = sql_attempts + 1
                state["last_sql_error"] = error_msg
                # The graph will retry this node
                return state
            else:
                state["error"] = error_msg
                state["response"] = format_error_response(question, sql, error_msg)
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

    try:
        response = llm_explain.invoke([HumanMessage(content=prompt)])
        content = response.content
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content

    except Exception:
        return "Query executed successfully."


def format_error_response(question: str, sql: str, error: str) -> str:
    """Format error response in a user-friendly way."""
    return json.dumps({
        "error": True,
        "message": f"I tried to answer your question but encountered an error: {error}",
        "attempted_sql": sql,
        "suggestion": "Try rephrasing your question or asking about specific tables/columns.",
    })


def should_retry_generate(state: AgentState) -> str:
    """Determine if we should retry SQL generation or proceed to end."""
    sql_attempts = state.get("sql_attempts", 0)
    last_sql_error = state.get("last_sql_error")

    # If there's an error and we haven't exhausted retries, go back to generate
    if last_sql_error and sql_attempts > 0 and sql_attempts < MAX_SQL_RETRIES:
        if not state.get("response"):  # No final response yet
            return "generate"

    return "end"


def create_agent_graph() -> StateGraph:
    """Create the LangGraph agent workflow."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("understand", understand_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("enrich", enrich_node)
    workflow.add_node("search_values", search_values_node)
    workflow.add_node("generate", generate_node)

    # Define edges
    workflow.set_entry_point("understand")
    workflow.add_edge("understand", "retrieve")
    workflow.add_edge("retrieve", "enrich")
    workflow.add_edge("enrich", "search_values")
    workflow.add_edge("search_values", "generate")

    # Conditional edge for retry logic
    workflow.add_conditional_edges(
        "generate",
        should_retry_generate,
        {
            "generate": "generate",  # Retry
            "end": END,  # Done
        },
    )

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
        searchable_terms=None,
        relevant_tables=None,
        table_insights=None,
        resolved_values=None,
        generated_sql=None,
        sql_attempts=0,
        last_sql_error=None,
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
