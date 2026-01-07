"""
Metadata Extractor

Extracts schema information, statistics, and metadata from PostgreSQL databases.
"""

import asyncio
from dataclasses import dataclass, field

import asyncpg

from app.config import get_settings

settings = get_settings()


@dataclass
class ColumnInfo:
    """Information about a database column."""

    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool = False
    is_foreign_key: bool = False
    foreign_key_ref: str | None = None
    distinct_count: int | None = None
    null_count: int | None = None
    categorical_values: list[str] | None = None
    sample_values: list[str] | None = None


@dataclass
class TableInfo:
    """Information about a database table."""

    schema_name: str
    table_name: str
    row_count: int
    columns: list[ColumnInfo] = field(default_factory=list)
    primary_keys: list[str] = field(default_factory=list)
    foreign_keys: list[dict] = field(default_factory=list)


@dataclass
class DatabaseMetadata:
    """Complete metadata for a database."""

    tables: list[TableInfo] = field(default_factory=list)
    total_tables: int = 0
    total_rows: int = 0


async def get_connection(
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    ssl_mode: str = "prefer",
) -> asyncpg.Connection:
    """Create a database connection."""
    ssl_map = {
        "disable": False,
        "allow": "prefer",
        "prefer": "prefer",
        "require": True,
        "verify-ca": True,
        "verify-full": True,
    }

    return await asyncpg.connect(
        host=host,
        port=port,
        database=database,
        user=username,
        password=password,
        ssl=ssl_map.get(ssl_mode, "prefer"),
    )


async def get_tables(conn: asyncpg.Connection, schema: str = "public") -> list[dict]:
    """Get all tables in a schema."""
    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = $1
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """
    rows = await conn.fetch(query, schema)
    return [{"schema": schema, "name": row["table_name"]} for row in rows]


async def get_columns(conn: asyncpg.Connection, schema: str, table: str) -> list[dict]:
    """Get column information for a table."""
    query = """
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = $1
        AND table_name = $2
        ORDER BY ordinal_position
    """
    rows = await conn.fetch(query, schema, table)
    return [
        {
            "name": row["column_name"],
            "data_type": row["data_type"],
            "is_nullable": row["is_nullable"] == "YES",
        }
        for row in rows
    ]


async def get_primary_keys(conn: asyncpg.Connection, schema: str, table: str) -> list[str]:
    """Get primary key columns for a table."""
    query = """
        SELECT a.attname as column_name
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        JOIN pg_class c ON c.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE i.indisprimary
        AND n.nspname = $1
        AND c.relname = $2
    """
    rows = await conn.fetch(query, schema, table)
    return [row["column_name"] for row in rows]


async def get_foreign_keys(conn: asyncpg.Connection, schema: str, table: str) -> list[dict]:
    """Get foreign key relationships for a table."""
    query = """
        SELECT
            kcu.column_name,
            ccu.table_schema AS foreign_table_schema,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_schema = $1
        AND tc.table_name = $2
    """
    rows = await conn.fetch(query, schema, table)
    return [
        {
            "column": row["column_name"],
            "references": f"{row['foreign_table_schema']}.{row['foreign_table_name']}.{row['foreign_column_name']}",
        }
        for row in rows
    ]


async def get_row_count(conn: asyncpg.Connection, schema: str, table: str) -> int:
    """Get approximate row count for a table."""
    # Use pg_class for fast approximate count
    query = """
        SELECT reltuples::bigint AS estimate
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = $1
        AND c.relname = $2
    """
    result = await conn.fetchval(query, schema, table)

    # If estimate is 0 or very small, do an actual count
    if result is None or result < 100:
        count_query = f'SELECT COUNT(*) FROM "{schema}"."{table}"'
        result = await conn.fetchval(count_query)

    return result or 0


async def get_column_stats(
    conn: asyncpg.Connection, schema: str, table: str, column: str, row_count: int
) -> tuple[int, int, list[str] | None, list[str] | None]:
    """
    Get column statistics: distinct count, null count, and values.

    Returns: (distinct_count, null_count, categorical_values, sample_values)
    """
    # Get distinct count and null count
    stats_query = f"""
        SELECT
            COUNT(DISTINCT "{column}") as distinct_count,
            COUNT(*) FILTER (WHERE "{column}" IS NULL) as null_count
        FROM "{schema}"."{table}"
    """

    try:
        stats = await asyncio.wait_for(conn.fetchrow(stats_query), timeout=30.0)
        distinct_count = stats["distinct_count"]
        null_count = stats["null_count"]
    except asyncio.TimeoutError:
        # For very large tables, use approximation
        distinct_count = None
        null_count = None

    if distinct_count is None:
        return 0, 0, None, None

    threshold = settings.category_threshold
    sample_size = settings.sample_size

    categorical_values = None
    sample_values = None

    if distinct_count <= threshold and distinct_count > 0:
        # Categorical column - fetch all distinct values
        values_query = f"""
            SELECT DISTINCT "{column}"::text
            FROM "{schema}"."{table}"
            WHERE "{column}" IS NOT NULL
            ORDER BY "{column}"::text
            LIMIT {threshold}
        """
        try:
            rows = await asyncio.wait_for(conn.fetch(values_query), timeout=10.0)
            categorical_values = [row[0] for row in rows if row[0] is not None]
        except (asyncio.TimeoutError, Exception):
            categorical_values = None

    elif distinct_count > threshold:
        # High cardinality - sample random values
        sample_query = f"""
            SELECT "{column}"::text
            FROM "{schema}"."{table}"
            WHERE "{column}" IS NOT NULL
            ORDER BY RANDOM()
            LIMIT {sample_size}
        """
        try:
            rows = await asyncio.wait_for(conn.fetch(sample_query), timeout=10.0)
            sample_values = [row[0] for row in rows if row[0] is not None]
        except (asyncio.TimeoutError, Exception):
            sample_values = None

    return distinct_count, null_count or 0, categorical_values, sample_values


async def extract_metadata(
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    ssl_mode: str = "prefer",
    progress_callback: callable = None,
) -> DatabaseMetadata:
    """
    Extract complete metadata from a PostgreSQL database.

    Args:
        progress_callback: Optional callback function(progress: float, message: str)
    """
    conn = await get_connection(host, port, database, username, password, ssl_mode)

    try:
        metadata = DatabaseMetadata()

        # Get all tables
        tables = await get_tables(conn)
        metadata.total_tables = len(tables)

        if progress_callback:
            await progress_callback(5.0, f"Found {len(tables)} tables")

        for i, table_info in enumerate(tables):
            schema = table_info["schema"]
            table = table_info["name"]

            # Get basic table info
            row_count = await get_row_count(conn, schema, table)
            columns_raw = await get_columns(conn, schema, table)
            primary_keys = await get_primary_keys(conn, schema, table)
            foreign_keys = await get_foreign_keys(conn, schema, table)

            # Build column info with stats
            columns = []
            for col_raw in columns_raw:
                # Get column stats
                distinct, nulls, cat_vals, sample_vals = await get_column_stats(
                    conn, schema, table, col_raw["name"], row_count
                )

                # Check if foreign key
                fk_ref = None
                for fk in foreign_keys:
                    if fk["column"] == col_raw["name"]:
                        fk_ref = fk["references"]
                        break

                col = ColumnInfo(
                    name=col_raw["name"],
                    data_type=col_raw["data_type"],
                    is_nullable=col_raw["is_nullable"],
                    is_primary_key=col_raw["name"] in primary_keys,
                    is_foreign_key=fk_ref is not None,
                    foreign_key_ref=fk_ref,
                    distinct_count=distinct,
                    null_count=nulls,
                    categorical_values=cat_vals,
                    sample_values=sample_vals,
                )
                columns.append(col)

            table_obj = TableInfo(
                schema_name=schema,
                table_name=table,
                row_count=row_count,
                columns=columns,
                primary_keys=primary_keys,
                foreign_keys=foreign_keys,
            )
            metadata.tables.append(table_obj)
            metadata.total_rows += row_count

            # Progress update
            progress = 5.0 + (i + 1) / len(tables) * 45.0  # 5-50% for extraction
            if progress_callback:
                await progress_callback(progress, f"Analyzed table {table} ({i + 1}/{len(tables)})")

        return metadata

    finally:
        await conn.close()


def table_to_document(table: TableInfo) -> str:
    """Convert table info to a text document for vectorization."""
    lines = [
        f"# Table: {table.schema_name}.{table.table_name}",
        "",
        f"Row count: {table.row_count:,}",
        "",
        "## Columns",
    ]

    for col in table.columns:
        col_desc = [f"- **{col.name}** ({col.data_type})"]

        if col.is_primary_key:
            col_desc.append("  - Primary Key")
        if col.is_foreign_key:
            col_desc.append(f"  - Foreign Key → {col.foreign_key_ref}")
        if col.distinct_count is not None:
            col_desc.append(f"  - Distinct values: {col.distinct_count:,}")
        if col.categorical_values:
            values_str = ", ".join(col.categorical_values[:20])
            if len(col.categorical_values) > 20:
                values_str += f"... (+{len(col.categorical_values) - 20} more)"
            col_desc.append(f"  - Possible values: {values_str}")
        if col.sample_values:
            samples = ", ".join(col.sample_values[:5])
            col_desc.append(f"  - Sample values: {samples}")

        lines.extend(col_desc)

    if table.foreign_keys:
        lines.append("")
        lines.append("## Relationships")
        for fk in table.foreign_keys:
            lines.append(f"- {fk['column']} → {fk['references']}")

    return "\n".join(lines)
