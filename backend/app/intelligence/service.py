"""
Intelligence Service

Orchestrates the full database analysis workflow:
1. Extract metadata from database
2. Generate insights and documents
3. Determine indexing strategies
4. Store embeddings in vector database
"""

import json
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_settings
from app.connections.models import (
    ColumnMetadata,
    ConnectionStatus,
    DatabaseConnection,
    IndexingStrategy,
    TableInsight,
)
from app.connections.service import decrypt_password
from app.database import get_session_context
from app.intelligence.extractor import (
    ColumnInfo,
    TableInfo,
    _generate_column_summary,
    extract_metadata,
    table_to_document,
)
from app.intelligence.indexer import determine_indexing_strategy_llm
from app.intelligence.vectorizer import (
    delete_connection_documents,
    upsert_document,
)

settings = get_settings()


async def get_connection_for_analysis(connection_id: int) -> DatabaseConnection | None:
    """Get a connection by ID for analysis."""
    async with get_session_context() as session:
        stmt = select(DatabaseConnection).where(DatabaseConnection.id == connection_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def save_table_insight(
    session: AsyncSession,
    connection_id: int,
    table: TableInfo,
    document: str,
    vector_id: str,
) -> TableInsight:
    """Save table insight to database."""
    # Check if insight exists
    stmt = select(TableInsight).where(
        TableInsight.connection_id == connection_id,
        TableInsight.schema_name == table.schema_name,
        TableInsight.table_name == table.table_name,
    )
    result = await session.execute(stmt)
    insight = result.scalar_one_or_none()

    if insight:
        # Update existing
        insight.row_count = table.row_count
        insight.insight_document = document
        insight.vector_id = vector_id
        insight.updated_at = datetime.utcnow()
    else:
        # Create new
        insight = TableInsight(
            connection_id=connection_id,
            schema_name=table.schema_name,
            table_name=table.table_name,
            row_count=table.row_count,
            insight_document=document,
            vector_id=vector_id,
        )
        session.add(insight)

    await session.commit()
    await session.refresh(insight)
    return insight


async def save_column_metadata(
    session: AsyncSession,
    table_insight_id: int,
    column: ColumnInfo,
    strategy: IndexingStrategy,
    table_name: str,
) -> ColumnMetadata:
    """Save column metadata to database."""
    # Generate column summary
    column_summary = _generate_column_summary(column, table_name)

    # Check if exists
    stmt = select(ColumnMetadata).where(
        ColumnMetadata.table_insight_id == table_insight_id,
        ColumnMetadata.column_name == column.name,
    )
    result = await session.execute(stmt)
    metadata = result.scalar_one_or_none()

    if metadata:
        # Update
        metadata.data_type = column.data_type
        metadata.is_nullable = column.is_nullable
        metadata.is_primary_key = column.is_primary_key
        metadata.is_foreign_key = column.is_foreign_key
        metadata.foreign_key_ref = column.foreign_key_ref
        metadata.distinct_count = column.distinct_count
        metadata.null_count = column.null_count
        metadata.indexing_strategy = strategy
        metadata.categorical_values = (
            json.dumps(column.categorical_values) if column.categorical_values else None
        )
        metadata.sample_values = (
            json.dumps(column.sample_values) if column.sample_values else None
        )
        metadata.column_summary = column_summary
    else:
        # Create
        metadata = ColumnMetadata(
            table_insight_id=table_insight_id,
            column_name=column.name,
            data_type=column.data_type,
            is_nullable=column.is_nullable,
            is_primary_key=column.is_primary_key,
            is_foreign_key=column.is_foreign_key,
            foreign_key_ref=column.foreign_key_ref,
            distinct_count=column.distinct_count,
            null_count=column.null_count,
            indexing_strategy=strategy,
            categorical_values=(
                json.dumps(column.categorical_values) if column.categorical_values else None
            ),
            sample_values=json.dumps(column.sample_values) if column.sample_values else None,
            column_summary=column_summary,
        )
        session.add(metadata)

    await session.commit()
    return metadata


async def analyze_database(connection_id: int) -> None:
    """
    Full database analysis workflow.

    This is the main orchestration function that:
    1. Extracts metadata from the database
    2. Generates insights for each table
    3. Determines indexing strategies using LLM
    4. Stores embeddings in Qdrant
    """
    async with get_session_context() as session:
        # Get connection
        stmt = select(DatabaseConnection).where(DatabaseConnection.id == connection_id)
        result = await session.execute(stmt)
        connection = result.scalar_one_or_none()

        if not connection:
            return

        # Update status
        connection.status = ConnectionStatus.ANALYZING
        connection.status_message = "Starting analysis..."
        connection.analysis_progress = 0.0
        session.add(connection)
        await session.commit()

        try:
            # Decrypt password
            password = decrypt_password(connection.encrypted_password)

            # Progress callback
            async def update_progress(progress: float, message: str) -> None:
                connection.analysis_progress = progress
                connection.status_message = message
                session.add(connection)
                await session.commit()

            # Extract metadata
            await update_progress(5.0, "Extracting database metadata...")

            metadata = await extract_metadata(
                host=connection.host,
                port=connection.port,
                database=connection.database,
                username=connection.username,
                password=password,
                ssl_mode=connection.ssl_mode,
                progress_callback=update_progress,
            )

            # Update status to indexing
            connection.status = ConnectionStatus.INDEXING
            await update_progress(50.0, "Generating insights and indexing...")

            # Delete old documents
            await delete_connection_documents(connection_id)

            # Process each table
            num_tables = len(metadata.tables)
            for i, table in enumerate(metadata.tables):
                table_progress = 50.0 + (i / num_tables) * 45.0
                await update_progress(
                    table_progress, f"Processing {table.table_name} ({i + 1}/{num_tables})..."
                )

                # Generate document
                document = table_to_document(table)

                # Build summary
                summary_parts = [
                    f"Table {table.schema_name}.{table.table_name}",
                    f"{table.row_count:,} rows",
                    f"{len(table.columns)} columns",
                ]
                if table.foreign_keys:
                    summary_parts.append(f"{len(table.foreign_keys)} foreign keys")

                # Upsert to vector store
                vector_id = await upsert_document(
                    connection_id=connection_id,
                    table_name=table.table_name,
                    schema_name=table.schema_name,
                    document=document,
                    metadata={
                        "row_count": table.row_count,
                        "column_count": len(table.columns),
                        "summary": " | ".join(summary_parts),
                    },
                )

                # Save table insight
                insight = await save_table_insight(
                    session, connection_id, table, document, vector_id
                )
                insight.summary = " | ".join(summary_parts)
                session.add(insight)
                await session.commit()

                # Process columns and determine indexing strategy
                for column in table.columns:
                    try:
                        strategy, _ = await determine_indexing_strategy_llm(
                            column, f"{table.table_name}: {table.row_count} rows"
                        )
                    except Exception:
                        # Fallback to rule-based
                        from app.intelligence.indexer import (
                            determine_indexing_strategy_rule_based,
                        )

                        strategy = determine_indexing_strategy_rule_based(column)

                    await save_column_metadata(
                        session, insight.id, column, strategy, table.table_name
                    )

            # Complete
            connection.status = ConnectionStatus.READY
            connection.status_message = "Analysis complete"
            connection.analysis_progress = 100.0
            connection.last_analyzed_at = datetime.utcnow()
            session.add(connection)
            await session.commit()

        except Exception as e:
            # Error handling
            connection.status = ConnectionStatus.ERROR
            connection.status_message = f"Analysis failed: {str(e)[:200]}"
            session.add(connection)
            await session.commit()
            raise


async def get_connection_insights(
    session: AsyncSession, connection_id: int
) -> list[dict]:
    """Get all insights for a connection."""
    stmt = select(TableInsight).where(TableInsight.connection_id == connection_id)
    result = await session.execute(stmt)
    insights = result.scalars().all()

    output = []
    for insight in insights:
        # Get columns
        col_stmt = select(ColumnMetadata).where(
            ColumnMetadata.table_insight_id == insight.id
        )
        col_result = await session.execute(col_stmt)
        columns = col_result.scalars().all()

        output.append(
            {
                "id": insight.id,
                "schema_name": insight.schema_name,
                "table_name": insight.table_name,
                "row_count": insight.row_count,
                "summary": insight.summary,
                "insight_document": insight.insight_document,
                "vector_id": insight.vector_id,
                "columns": [
                    {
                        "name": col.column_name,
                        "data_type": col.data_type,
                        "is_primary_key": col.is_primary_key,
                        "is_foreign_key": col.is_foreign_key,
                        "distinct_count": col.distinct_count,
                        "indexing_strategy": col.indexing_strategy.value,
                        "categorical_values": (
                            json.loads(col.categorical_values)
                            if col.categorical_values
                            else None
                        ),
                        "column_summary": col.column_summary,
                    }
                    for col in columns
                ],
            }
        )

    return output
