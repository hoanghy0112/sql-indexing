"""
RAG Tools

LangChain-compatible tools for searching and querying databases.
"""

import asyncio
import json
from typing import Any

import asyncpg
from langchain_core.tools import StructuredTool
from langchain_core.pydantic_v1 import BaseModel as LangchainBaseModel
from langchain_core.pydantic_v1 import Field as LangchainField

from app.config import get_settings
from app.intelligence.vectorizer import search_similar

settings = get_settings()


class SearchDatabaseInput(LangchainBaseModel):
    """Input schema for search_database_data tool."""

    query: str = LangchainField(description="The search query to find relevant tables and columns")
    connection_id: int = LangchainField(description="The database connection ID to search")
    limit: int = LangchainField(default=5, description="Maximum number of results to return")


class ExecuteSQLInput(LangchainBaseModel):
    """Input schema for execute_sql tool."""

    sql: str = LangchainField(description="The SQL query to execute")
    connection_id: int = LangchainField(description="The database connection ID")


# Store connection details in memory for tool execution
# In production, use a proper cache
_connection_cache: dict[int, dict] = {}


def set_connection_details(connection_id: int, details: dict) -> None:
    """Cache connection details for tool execution."""
    _connection_cache[connection_id] = details


def get_connection_details(connection_id: int) -> dict | None:
    """Get cached connection details."""
    return _connection_cache.get(connection_id)


async def search_database_data(
    query: str,
    connection_id: int,
    limit: int = 5,
) -> str:
    """
    Search for relevant tables and columns based on semantic similarity.

    This tool queries the vector database to find tables and columns
    that are semantically similar to the user's query.

    Returns:
        JSON string with matching tables, their schemas, and relevance scores.
    """
    try:
        results = await search_similar(
            query=query,
            connection_id=connection_id,
            limit=limit,
        )

        if not results:
            return json.dumps({
                "status": "no_results",
                "message": "No relevant tables found for this query",
                "results": [],
            })

        formatted_results = []
        for result in results:
            formatted_results.append({
                "table_name": result["table_name"],
                "schema_name": result["schema_name"],
                "relevance_score": round(result["score"], 3),
                "document": result["document"][:1000] if result["document"] else None,
            })

        return json.dumps({
            "status": "success",
            "message": f"Found {len(formatted_results)} relevant tables",
            "results": formatted_results,
        })

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Search failed: {str(e)}",
            "results": [],
        })


async def execute_sql_query(
    sql: str,
    connection_id: int,
    max_rows: int = 100,
) -> dict[str, Any]:
    """
    Execute a SQL query on the user's database.

    Returns:
        Dict with columns, rows, and metadata.
    """
    details = get_connection_details(connection_id)
    if not details:
        return {
            "status": "error",
            "message": "Connection details not found",
            "columns": [],
            "rows": [],
        }

    try:
        ssl_map = {
            "disable": False,
            "prefer": "prefer",
            "require": True,
        }

        max_retries = 3
        retry_delay = 1.0
        last_error = None

        for attempt in range(max_retries):
            conn = None
            try:
                # 1. Connect
                conn = await asyncpg.connect(
                    host=details["host"],
                    port=details["port"],
                    database=details["database"],
                    user=details["username"],
                    password=details["password"],
                    ssl=ssl_map.get(details.get("ssl_mode", "prefer"), "prefer"),
                    timeout=20.0,
                    command_timeout=60.0,
                )

                # 2. Execute query
                rows = await conn.fetch(sql, timeout=60.0)

                # 3. Process results
                if not rows:
                    return {
                        "status": "success",
                        "message": "Query executed but returned no rows",
                        "columns": [],
                        "rows": [],
                        "row_count": 0,
                    }

                columns = list(rows[0].keys())
                data = []
                for row in rows[:max_rows]:
                    data.append([_serialize_value(row[col]) for col in columns])

                return {
                    "status": "success",
                    "message": f"Returned {len(data)} rows (attempt {attempt + 1})",
                    "columns": columns,
                    "rows": data,
                    "row_count": len(rows),
                    "truncated": len(rows) > max_rows,
                }

            except (asyncpg.PostgresConnectionError, asyncpg.InterfaceError, asyncio.TimeoutError) as e:
                last_error = e
                if "unexpected connection_lost" in str(e).lower() or isinstance(e, asyncio.TimeoutError):
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue
                break
            except asyncpg.PostgresSyntaxError as e:
                return {
                    "status": "error",
                    "message": f"SQL syntax error: {str(e)}",
                    "columns": [],
                    "rows": [],
                }
            except Exception as e:
                last_error = e
                break
            finally:
                if conn:
                    await conn.close()

        return {
            "status": "error",
            "message": f"Query failed after {max_retries} attempts: {str(last_error)}",
            "columns": [],
            "rows": [],
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Query failed: {str(e)}",
            "columns": [],
            "rows": [],
        }


def _serialize_value(value: Any) -> Any:
    """Serialize a database value to JSON-compatible format."""
    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    # Convert other types to string
    return str(value)


def rows_to_csv(columns: list[str], rows: list[list]) -> str:
    """Convert query results to CSV format."""
    lines = [",".join(columns)]
    for row in rows:
        # Escape values
        escaped = []
        for val in row:
            if val is None:
                escaped.append("")
            elif isinstance(val, str):
                # Escape quotes and wrap in quotes if needed
                if "," in val or '"' in val or "\n" in val:
                    val = val.replace('"', '""')
                    escaped.append(f'"{val}"')
                else:
                    escaped.append(val)
            else:
                escaped.append(str(val))
        lines.append(",".join(escaped))
    return "\n".join(lines)


# Create LangChain tools
search_database_tool = StructuredTool.from_function(
    coroutine=search_database_data,
    name="search_database_data",
    description="""
    Search for relevant tables and columns in a database based on a natural language query.
    Use this tool to understand what data is available before writing SQL queries.
    Returns table names, schemas, and document summaries with relevance scores.
    """,
    args_schema=SearchDatabaseInput,
)
