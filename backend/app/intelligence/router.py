"""
Intelligence Router

API endpoints for the intelligence engine: insights, analysis status, and progress.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.auth.dependencies import CurrentUser, DBSession
from app.auth.schemas import MessageResponse
from app.connections.service import get_connection_by_id, user_can_access_connection
from app.intelligence.service import get_connection_insights
from app.intelligence.vectorizer import get_collection_stats

router = APIRouter()


class InsightResponse(BaseModel):
    """Response for table insight."""

    id: int
    schema_name: str
    table_name: str
    row_count: int
    summary: str | None
    insight_document: str | None
    columns: list[dict]


class IndexStatsResponse(BaseModel):
    """Response for index statistics."""

    vectors_count: int
    indexed_vectors_count: int
    points_count: int
    status: str
    tables_analyzed: int
    total_rows: int


class UpdateInsightRequest(BaseModel):
    """Request to update an insight."""

    summary: str | None = None
    insight_document: str | None = None


@router.get("/{connection_id}/insights", response_model=list[InsightResponse])
async def list_insights(
    connection_id: int,
    current_user: CurrentUser,
    session: DBSession,
) -> list[InsightResponse]:
    """Get all table insights for a connection."""
    can_access, _ = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    insights = await get_connection_insights(session, connection_id)

    return [
        InsightResponse(
            id=insight["id"],
            schema_name=insight["schema_name"],
            table_name=insight["table_name"],
            row_count=insight["row_count"],
            summary=insight["summary"],
            insight_document=insight["insight_document"],
            columns=insight["columns"],
        )
        for insight in insights
    ]


@router.get("/{connection_id}/stats", response_model=IndexStatsResponse)
async def get_index_stats(
    connection_id: int,
    current_user: CurrentUser,
    session: DBSession,
) -> IndexStatsResponse:
    """Get indexing statistics for a connection."""
    can_access, _ = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    # Get vector store stats
    vector_stats = await get_collection_stats()

    # Get connection insights
    insights = await get_connection_insights(session, connection_id)
    total_rows = sum(i["row_count"] for i in insights)

    return IndexStatsResponse(
        vectors_count=vector_stats.get("vectors_count", 0),
        indexed_vectors_count=vector_stats.get("indexed_vectors_count", 0),
        points_count=vector_stats.get("points_count", 0),
        status=vector_stats.get("status", "unknown"),
        tables_analyzed=len(insights),
        total_rows=total_rows,
    )


@router.put("/{connection_id}/insights/{insight_id}", response_model=MessageResponse)
async def update_insight(
    connection_id: int,
    insight_id: int,
    update_data: UpdateInsightRequest,
    current_user: CurrentUser,
    session: DBSession,
) -> MessageResponse:
    """Update an insight (edit summary or document)."""
    can_access, can_edit = await user_can_access_connection(
        session, current_user, connection_id
    )
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )
    if not can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit insights",
        )

    from sqlmodel import select

    from app.connections.models import TableInsight

    stmt = select(TableInsight).where(
        TableInsight.id == insight_id,
        TableInsight.connection_id == connection_id,
    )
    result = await session.execute(stmt)
    insight = result.scalar_one_or_none()

    if not insight:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insight not found",
        )

    if update_data.summary is not None:
        insight.summary = update_data.summary
    if update_data.insight_document is not None:
        insight.insight_document = update_data.insight_document

    session.add(insight)
    await session.commit()

    return MessageResponse(message="Insight updated successfully")


@router.get("/{connection_id}/progress")
async def get_analysis_progress(
    connection_id: int,
    current_user: CurrentUser,
    session: DBSession,
):
    """
    Server-Sent Events endpoint for real-time analysis progress.

    Returns a stream of progress updates.
    """
    can_access, _ = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    import asyncio
    import json

    async def event_generator():
        while True:
            # Get current status
            connection = await get_connection_by_id(session, connection_id)
            if not connection:
                break

            data = {
                "status": connection.status.value,
                "progress": connection.analysis_progress,
                "message": connection.status_message,
            }

            yield {"event": "progress", "data": json.dumps(data)}

            # Stop if complete or error
            if connection.status in ["ready", "error"]:
                break

            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())
