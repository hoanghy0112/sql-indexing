"""
Indexer

LLM-based decision logic for determining indexing strategies.
Uses Ollama with qwen3:4b for intelligent decisions.
"""

import json
import re

import ollama

from app.config import get_settings
from app.connections.models import IndexingStrategy
from app.intelligence.extractor import ColumnInfo

settings = get_settings()


def determine_indexing_strategy_rule_based(column: ColumnInfo) -> IndexingStrategy:
    """
    Rule-based fallback for determining indexing strategy.

    Used when LLM is unavailable or for simple cases.
    """
    # Skip primary keys, foreign keys, and ID-like columns
    if column.is_primary_key or column.is_foreign_key:
        return IndexingStrategy.SKIP

    # Skip common non-searchable types
    skip_types = [
        "timestamp",
        "date",
        "time",
        "boolean",
        "bytea",
        "json",
        "jsonb",
        "uuid",
        "inet",
        "macaddr",
    ]
    if any(skip_type in column.data_type.lower() for skip_type in skip_types):
        return IndexingStrategy.SKIP

    # Skip numeric types that are likely IDs
    if column.data_type.lower() in ["integer", "bigint", "smallint", "serial", "bigserial"]:
        if "id" in column.name.lower() or "count" in column.name.lower():
            return IndexingStrategy.SKIP

    # If we have distinct count
    if column.distinct_count is not None:
        threshold = settings.category_threshold

        # Very low cardinality - categorical
        if column.distinct_count <= threshold:
            return IndexingStrategy.CATEGORICAL

        # High cardinality text - vector index
        if column.data_type.lower() in ["text", "character varying", "varchar", "char"]:
            return IndexingStrategy.VECTOR

    # Default: skip
    return IndexingStrategy.SKIP


async def determine_indexing_strategy_llm(
    column: ColumnInfo, table_context: str
) -> tuple[IndexingStrategy, str]:
    """
    Use LLM to determine the optimal indexing strategy for a column.

    Returns (strategy, reasoning).
    """
    # Build prompt
    prompt = f"""You are a database indexing expert. Analyze this column and decide the best indexing strategy.

Table Context:
{table_context}

Column to analyze:
- Name: {column.name}
- Data Type: {column.data_type}
- Is Nullable: {column.is_nullable}
- Is Primary Key: {column.is_primary_key}
- Is Foreign Key: {column.is_foreign_key}
- Distinct Values: {column.distinct_count if column.distinct_count else 'Unknown'}
- Null Count: {column.null_count if column.null_count else 'Unknown'}
- Sample Values: {column.sample_values[:5] if column.sample_values else column.categorical_values[:10] if column.categorical_values else 'None'}

Choose ONE indexing strategy:
1. CATEGORICAL - Low cardinality column (< 100 distinct values). Good for enums, status fields, categories. Store all values in metadata.
2. VECTOR - High cardinality text column. Good for descriptions, names, comments. Will be vector-indexed for semantic search.
3. SKIP - IDs, timestamps, numbers, or columns not useful for text search.

Respond in JSON format only:
{{"strategy": "CATEGORICAL|VECTOR|SKIP", "reasoning": "brief explanation"}}
"""

    try:
        response = ollama.chat(
            model=settings.ollama_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 200},
        )

        content = response["message"]["content"]

        # Find the json part in response (handle /think tags from qwen3)
        json_match = re.search(r'\{[^{}]*"strategy"[^{}]*\}', content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            # Try to parse the whole content
            result = json.loads(content)

        strategy_map = {
            "CATEGORICAL": IndexingStrategy.CATEGORICAL,
            "VECTOR": IndexingStrategy.VECTOR,
            "SKIP": IndexingStrategy.SKIP,
        }

        strategy = strategy_map.get(result.get("strategy", "").upper(), IndexingStrategy.SKIP)
        reasoning = result.get("reasoning", "LLM decision")

        return strategy, reasoning

    except Exception as e:
        # Fallback to rule-based
        strategy = determine_indexing_strategy_rule_based(column)
        return strategy, f"Fallback to rule-based (LLM error: {str(e)[:50]})"


async def check_category_overflow(
    current_values: list[str], new_values: list[str]
) -> tuple[bool, list[str] | None]:
    """
    Check if a categorical column has overflowed (too many new values).

    Returns (should_convert_to_vector, updated_values_if_still_categorical).
    """
    threshold = settings.category_threshold

    # Combine and deduplicate
    all_values = list(set(current_values + new_values))

    if len(all_values) > threshold:
        # Overflow - should convert to vector indexing
        return True, None

    # Still categorical - return updated values
    return False, all_values


async def generate_indexing_report(columns: list[tuple[ColumnInfo, IndexingStrategy]]) -> str:
    """Generate a human-readable report of indexing decisions."""
    report_lines = ["# Indexing Strategy Report", ""]

    categorical = [(c, s) for c, s in columns if s == IndexingStrategy.CATEGORICAL]
    vector = [(c, s) for c, s in columns if s == IndexingStrategy.VECTOR]
    skipped = [(c, s) for c, s in columns if s == IndexingStrategy.SKIP]

    if categorical:
        report_lines.append(f"## Categorical Columns ({len(categorical)})")
        report_lines.append("These columns have low cardinality. All values stored in metadata.")
        for col, _ in categorical:
            val_count = len(col.categorical_values) if col.categorical_values else "?"
            report_lines.append(f"- **{col.name}** ({val_count} values)")
        report_lines.append("")

    if vector:
        report_lines.append(f"## Vector-Indexed Columns ({len(vector)})")
        report_lines.append("These columns are indexed for semantic search.")
        for col, _ in vector:
            report_lines.append(f"- **{col.name}** ({col.data_type})")
        report_lines.append("")

    if skipped:
        report_lines.append(f"## Skipped Columns ({len(skipped)})")
        report_lines.append("These columns are not indexed (IDs, timestamps, etc).")
        for col, _ in skipped:
            report_lines.append(f"- {col.name}")
        report_lines.append("")

    return "\n".join(report_lines)
