"""
RAG Tools

LangChain-compatible tools for searching and querying databases.
"""

import asyncio
import json
from typing import Any

import asyncpg
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.config import get_settings
from app.database import get_session_context
from app.intelligence.vectorizer import embed_text, search_similar

settings = get_settings()


class SearchDatabaseInput(BaseModel):
    """Input schema for search_database_data tool."""

    query: str = Field(description="The search query to find relevant tables and columns")
    connection_id: int = Field(description="The database connection ID to search")
    limit: int = Field(default=5, description="Maximum number of results to return")


class ExecuteSQLInput(BaseModel):
    """Input schema for execute_sql tool."""

    sql: str = Field(description="The SQL query to execute")
    connection_id: int = Field(description="The database connection ID")


class GetTableInsightsInput(BaseModel):
    """Input schema for get_table_insights tool."""

    connection_id: int = Field(description="The database connection ID")
    table_names: list[str] = Field(
        description="List of table names to get insights for"
    )


class SearchByIndexInput(BaseModel):
    """Input schema for search_by_index tool."""

    connection_id: int = Field(description="The database connection ID")
    table_name: str = Field(description="The table name to search in")
    column_name: str = Field(description="The column name to search")
    search_term: str = Field(
        description="The term to search for (can be synonym or approximate value)"
    )


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


async def get_table_insights(
    connection_id: int,
    table_names: list[str],
) -> str:
    """
    Get detailed insights for specified tables from the database.

    This tool fetches rich metadata about tables including:
    - Table summary and purpose
    - Column information (type, nullability, keys)
    - Categorical values for low-cardinality columns
    - Sample values for high-cardinality columns
    - AI-generated column descriptions

    Use this BEFORE generating SQL to understand the exact column names,
    data types, and available values.

    Returns:
        JSON string with detailed table and column metadata.
    """
    # Import here to avoid circular dependency
    from app.connections.models import ColumnMetadata, TableInsight

    try:
        async with get_session_context() as session:
            from sqlmodel import select

            # Fetch table insights
            stmt = select(TableInsight).where(
                TableInsight.connection_id == connection_id,
                TableInsight.table_name.in_(table_names),
            )
            result = await session.execute(stmt)
            table_insights = result.scalars().all()

            if not table_insights:
                return json.dumps({
                    "status": "no_results",
                    "message": f"No insights found for tables: {table_names}",
                    "tables": [],
                })

            tables_data = []
            for table in table_insights:
                # Fetch columns for this table
                col_stmt = select(ColumnMetadata).where(
                    ColumnMetadata.table_insight_id == table.id
                )
                col_result = await session.execute(col_stmt)
                columns = col_result.scalars().all()

                columns_data = []
                for col in columns:
                    col_info = {
                        "column_name": col.column_name,
                        "data_type": col.data_type,
                        "is_nullable": col.is_nullable,
                        "is_primary_key": col.is_primary_key,
                        "is_foreign_key": col.is_foreign_key,
                        "foreign_key_ref": col.foreign_key_ref,
                        "indexing_strategy": col.indexing_strategy.value if col.indexing_strategy else None,
                        "distinct_count": col.distinct_count,
                        "column_summary": col.column_summary,
                    }

                    # Include categorical values for agent to know exact options
                    if col.categorical_values:
                        try:
                            col_info["categorical_values"] = json.loads(col.categorical_values)
                        except json.JSONDecodeError:
                            col_info["categorical_values"] = None

                    # Include sample values for reference
                    if col.sample_values:
                        try:
                            col_info["sample_values"] = json.loads(col.sample_values)[:10]
                        except json.JSONDecodeError:
                            col_info["sample_values"] = None

                    columns_data.append(col_info)

                tables_data.append({
                    "table_name": table.table_name,
                    "schema_name": table.schema_name,
                    "row_count": table.row_count,
                    "summary": table.summary,
                    "columns": columns_data,
                })

            return json.dumps({
                "status": "success",
                "message": f"Found insights for {len(tables_data)} tables",
                "tables": tables_data,
            })

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Failed to get table insights: {str(e)}",
            "tables": [],
        })


async def search_by_index(
    connection_id: int,
    table_name: str,
    column_name: str,
    search_term: str,
    limit: int = 10,
) -> str:
    """
    Search for actual data values using categorical or vector indexes.

    Use this tool when:
    - User mentions a value that might be a synonym (e.g., "NYC" for "New York")
    - User uses approximate terms that need to be resolved to actual values
    - You need to find the exact value to use in a WHERE clause

    For CATEGORICAL columns: Searches through stored categorical values
    For VECTOR columns: Uses semantic similarity on sample values

    Returns:
        JSON with matching values and similarity scores.
    """
    from app.connections.models import ColumnMetadata, IndexingStrategy, TableInsight

    try:
        async with get_session_context() as session:
            from sqlmodel import select

            # Find the table insight
            stmt = select(TableInsight).where(
                TableInsight.connection_id == connection_id,
                TableInsight.table_name == table_name,
            )
            result = await session.execute(stmt)
            table_insight = result.scalar_one_or_none()

            if not table_insight:
                return json.dumps({
                    "status": "error",
                    "message": f"Table '{table_name}' not found",
                    "matches": [],
                })

            # Find the column metadata
            col_stmt = select(ColumnMetadata).where(
                ColumnMetadata.table_insight_id == table_insight.id,
                ColumnMetadata.column_name == column_name,
            )
            col_result = await session.execute(col_stmt)
            column = col_result.scalar_one_or_none()

            if not column:
                return json.dumps({
                    "status": "error",
                    "message": f"Column '{column_name}' not found in table '{table_name}'",
                    "matches": [],
                })

            matches = []
            search_term_lower = search_term.lower()

            if column.indexing_strategy == IndexingStrategy.CATEGORICAL:
                # Search through categorical values
                if column.categorical_values:
                    try:
                        values = json.loads(column.categorical_values)
                        for value in values:
                            if value is None:
                                continue
                            value_str = str(value).lower()
                            # Fuzzy matching: check if search term is contained or similar
                            if search_term_lower in value_str or value_str in search_term_lower:
                                matches.append({
                                    "value": value,
                                    "match_type": "contains",
                                    "score": 1.0,
                                })
                            elif _fuzzy_match(search_term_lower, value_str):
                                matches.append({
                                    "value": value,
                                    "match_type": "fuzzy",
                                    "score": 0.8,
                                })
                    except json.JSONDecodeError:
                        pass

            elif column.indexing_strategy == IndexingStrategy.VECTOR:
                # Use vector similarity on sample values
                if column.sample_values:
                    try:
                        values = json.loads(column.sample_values)
                        # Generate embedding for search term
                        search_embedding = await embed_text(search_term)

                        # Compare with each sample value
                        for value in values:
                            if value is None:
                                continue
                            value_embedding = await embed_text(str(value))
                            similarity = _cosine_similarity(search_embedding, value_embedding)

                            if similarity > 0.5:  # Threshold for relevance
                                matches.append({
                                    "value": value,
                                    "match_type": "semantic",
                                    "score": round(similarity, 3),
                                })
                    except json.JSONDecodeError:
                        pass

            # Sort by score and limit
            matches = sorted(matches, key=lambda x: x["score"], reverse=True)[:limit]

            if not matches:
                # Fallback: exact string search
                return json.dumps({
                    "status": "no_matches",
                    "message": f"No matches found for '{search_term}' in {table_name}.{column_name}. "
                               f"The column has indexing strategy: {column.indexing_strategy.value if column.indexing_strategy else 'none'}",
                    "matches": [],
                    "suggestion": "Try using the exact value or a different search term",
                })

            return json.dumps({
                "status": "success",
                "message": f"Found {len(matches)} matching values",
                "matches": matches,
                "column_info": {
                    "indexing_strategy": column.indexing_strategy.value if column.indexing_strategy else None,
                    "distinct_count": column.distinct_count,
                },
            })

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Search failed: {str(e)}",
            "matches": [],
        })


def _fuzzy_match(s1: str, s2: str) -> bool:
    """Simple fuzzy matching using common abbreviations and patterns."""
    # Common abbreviations
    abbreviations = {
        "nyc": "new york",
        "la": "los angeles",
        "sf": "san francisco",
        "usa": "united states",
        "uk": "united kingdom",
        "jr": "junior",
        "sr": "senior",
        "mgr": "manager",
        "dept": "department",
        "qty": "quantity",
        "amt": "amount",
    }

    # Check if s1 is an abbreviation of s2
    if s1 in abbreviations and abbreviations[s1] in s2:
        return True
    if s2 in abbreviations and abbreviations[s2] in s1:
        return True

    # Check Levenshtein-like similarity (simplified)
    if len(s1) > 3 and len(s2) > 3:
        # Check if they share a significant substring
        for i in range(len(s1) - 2):
            if s1[i:i+3] in s2:
                return True

    return False


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    import math

    dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


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
    if isinstance(value, int | float | str | bool):
        return value
    if isinstance(value, list | tuple):
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

get_table_insights_tool = StructuredTool.from_function(
    coroutine=get_table_insights,
    name="get_table_insights",
    description="""
    Get detailed insights for specified tables including column metadata,
    categorical values, sample values, and AI-generated summaries.
    Use this AFTER finding relevant tables to get exact column names and available values.
    This helps write accurate SQL queries.
    """,
    args_schema=GetTableInsightsInput,
)

search_by_index_tool = StructuredTool.from_function(
    coroutine=search_by_index,
    name="search_by_index",
    description="""
    Search for actual data values in a specific column using categorical or vector indexes.
    Use this when the user mentions values that might be synonyms or abbreviations
    (e.g., "NYC" for "New York City", "mgr" for "manager").
    Returns matching values with similarity scores to use in WHERE clauses.
    """,
    args_schema=SearchByIndexInput,
)
