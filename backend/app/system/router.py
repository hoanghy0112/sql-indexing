"""
System Router

System management APIs: health, status, SQL history.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlmodel import func, select

from app.agent.models import SQLHistory
from app.auth.dependencies import CurrentUser, DBSession
from app.connections.models import ConnectionStatus, DatabaseConnection
from app.connections.service import user_can_access_connection
from app.intelligence.vectorizer import get_collection_stats

router = APIRouter()


class SystemHealthResponse(BaseModel):
    """System health check response."""

    status: str
    database: str
    vector_store: dict
    version: str


class SQLHistoryItem(BaseModel):
    """SQL history item."""

    id: int
    query: str
    execution_time_ms: int | None
    row_count: int | None
    error: str | None
    created_at: str


class SQLHistoryResponse(BaseModel):
    """SQL history response."""

    items: list[SQLHistoryItem]
    total: int


class ConnectionStatusResponse(BaseModel):
    """Connection status response."""

    id: int
    name: str
    status: str
    status_message: str | None
    progress: float
    last_analyzed_at: str | None


@router.get("/health", response_model=SystemHealthResponse)
async def system_health() -> SystemHealthResponse:
    """Get overall system health."""
    from app.config import get_settings

    settings = get_settings()

    # Check vector store
    try:
        vector_stats = await get_collection_stats()
    except Exception as e:
        vector_stats = {"status": "error", "error": str(e)}

    return SystemHealthResponse(
        status="healthy",
        database="connected",
        vector_store=vector_stats,
        version=settings.app_version,
    )


@router.get("/connections/{connection_id}/status", response_model=ConnectionStatusResponse)
async def get_connection_status(
    connection_id: int,
    current_user: CurrentUser,
    session: DBSession,
) -> ConnectionStatusResponse:
    """Get status of a specific connection."""
    can_access, _ = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    stmt = select(DatabaseConnection).where(DatabaseConnection.id == connection_id)
    result = await session.execute(stmt)
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    return ConnectionStatusResponse(
        id=connection.id,
        name=connection.name,
        status=connection.status.value,
        status_message=connection.status_message,
        progress=connection.analysis_progress,
        last_analyzed_at=(
            connection.last_analyzed_at.isoformat() if connection.last_analyzed_at else None
        ),
    )


@router.get("/connections/{connection_id}/sql-history", response_model=SQLHistoryResponse)
async def get_sql_history(
    connection_id: int,
    current_user: CurrentUser,
    session: DBSession,
    limit: int = 50,
    offset: int = 0,
) -> SQLHistoryResponse:
    """Get SQL execution history for a connection."""
    can_access, _ = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    # Get total count
    count_stmt = select(func.count(SQLHistory.id)).where(
        SQLHistory.connection_id == connection_id,
        SQLHistory.user_id == current_user.id,
    )
    count_result = await session.execute(count_stmt)
    total = count_result.scalar() or 0

    # Get items
    stmt = (
        select(SQLHistory)
        .where(
            SQLHistory.connection_id == connection_id,
            SQLHistory.user_id == current_user.id,
        )
        .order_by(SQLHistory.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await session.execute(stmt)
    items = result.scalars().all()

    return SQLHistoryResponse(
        items=[
            SQLHistoryItem(
                id=item.id,
                query=item.query,
                execution_time_ms=item.execution_time_ms,
                row_count=item.row_count,
                error=item.error,
                created_at=item.created_at.isoformat(),
            )
            for item in items
        ],
        total=total,
    )


@router.get("/stats")
async def get_system_stats(
    current_user: CurrentUser,
    session: DBSession,
):
    """Get system-wide statistics for the current user."""
    # Count connections
    conn_stmt = select(func.count(DatabaseConnection.id)).where(
        DatabaseConnection.owner_id == current_user.id
    )
    conn_result = await session.execute(conn_stmt)
    connection_count = conn_result.scalar() or 0

    # Count ready connections
    ready_stmt = select(func.count(DatabaseConnection.id)).where(
        DatabaseConnection.owner_id == current_user.id,
        DatabaseConnection.status == ConnectionStatus.READY,
    )
    ready_result = await session.execute(ready_stmt)
    ready_count = ready_result.scalar() or 0

    # Count SQL queries
    sql_stmt = select(func.count(SQLHistory.id)).where(SQLHistory.user_id == current_user.id)
    sql_result = await session.execute(sql_stmt)
    query_count = sql_result.scalar() or 0

    return {
        "connections": {
            "total": connection_count,
            "ready": ready_count,
        },
        "queries": {
            "total": query_count,
        },
    }
