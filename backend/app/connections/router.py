"""
Database Connections Router

API endpoints for managing external database connections.
"""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlmodel import select

from app.auth.dependencies import CurrentUser, DBSession
from app.auth.schemas import MessageResponse
from app.connections.models import ConnectionShare, ConnectionStatus, DatabaseConnection, SharePermission
from app.connections.schemas import (
    ConnectionCreate,
    ConnectionFromURL,
    ConnectionListResponse,
    ConnectionResponse,
    ConnectionUpdate,
    ShareCreate,
    ShareListResponse,
    ShareResponse,
    TestConnectionResult,
)
from app.connections.service import (
    create_connection,
    delete_connection,
    decrypt_password,
    get_connection_by_id,
    get_user_connections,
    parse_connection_url,
    remove_share,
    share_connection,
    test_connection,
    update_connection_status,
    user_can_access_connection,
)
from app.users.models import User

router = APIRouter()


async def trigger_analysis(connection_id: int) -> None:
    """Trigger database analysis in background."""
    # This will be implemented in the intelligence module
    # Import here to avoid circular imports
    from app.intelligence.service import analyze_database

    await analyze_database(connection_id)


@router.post("", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
async def add_connection(
    connection_data: ConnectionCreate,
    current_user: CurrentUser,
    session: DBSession,
    background_tasks: BackgroundTasks,
) -> ConnectionResponse:
    """
    Add a new external PostgreSQL database connection.

    The database will be queued for analysis immediately after creation.
    """
    # Test connection first
    success, message, _ = await test_connection(
        host=connection_data.host,
        port=connection_data.port,
        database=connection_data.database,
        username=connection_data.username,
        password=connection_data.password,
        ssl_mode=connection_data.ssl_mode,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Connection test failed: {message}",
        )

    connection = await create_connection(
        session=session,
        owner=current_user,
        name=connection_data.name,
        host=connection_data.host,
        port=connection_data.port,
        database=connection_data.database,
        username=connection_data.username,
        password=connection_data.password,
        description=connection_data.description,
        ssl_mode=connection_data.ssl_mode,
    )

    # Trigger analysis in background
    background_tasks.add_task(trigger_analysis, connection.id)

    return ConnectionResponse(
        id=connection.id,
        name=connection.name,
        description=connection.description,
        host=connection.host,
        port=connection.port,
        database=connection.database,
        username=connection.username,
        ssl_mode=connection.ssl_mode,
        status=connection.status,
        status_message=connection.status_message,
        last_analyzed_at=connection.last_analyzed_at,
        analysis_progress=connection.analysis_progress,
        owner_id=connection.owner_id,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


@router.post("/from-url", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
async def add_connection_from_url(
    connection_data: ConnectionFromURL,
    current_user: CurrentUser,
    session: DBSession,
    background_tasks: BackgroundTasks,
) -> ConnectionResponse:
    """
    Add a new connection using a PostgreSQL connection URL.

    Format: postgresql://user:password@host:port/database
    """
    try:
        parsed = parse_connection_url(connection_data.connection_url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid connection URL: {e}",
        )

    # Test connection
    success, message, _ = await test_connection(
        host=parsed["host"],
        port=parsed["port"],
        database=parsed["database"],
        username=parsed["username"],
        password=parsed["password"],
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Connection test failed: {message}",
        )

    connection = await create_connection(
        session=session,
        owner=current_user,
        name=connection_data.name,
        host=parsed["host"],
        port=parsed["port"],
        database=parsed["database"],
        username=parsed["username"],
        password=parsed["password"],
        description=connection_data.description,
    )

    # Trigger analysis in background
    background_tasks.add_task(trigger_analysis, connection.id)

    return ConnectionResponse(
        id=connection.id,
        name=connection.name,
        description=connection.description,
        host=connection.host,
        port=connection.port,
        database=connection.database,
        username=connection.username,
        ssl_mode=connection.ssl_mode,
        status=connection.status,
        status_message=connection.status_message,
        last_analyzed_at=connection.last_analyzed_at,
        analysis_progress=connection.analysis_progress,
        owner_id=connection.owner_id,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


@router.get("", response_model=list[ConnectionListResponse])
async def list_connections(
    current_user: CurrentUser,
    session: DBSession,
) -> list[ConnectionListResponse]:
    """List all database connections accessible by the current user."""
    connections = await get_user_connections(session, current_user)

    return [
        ConnectionListResponse(
            id=conn.id,
            name=conn.name,
            description=conn.description,
            database=conn.database,
            status=conn.status,
            analysis_progress=conn.analysis_progress,
            last_analyzed_at=conn.last_analyzed_at,
            is_owner=is_owner,
            permission=permission,
        )
        for conn, is_owner, permission in connections
    ]


@router.get("/{connection_id}", response_model=ConnectionResponse)
async def get_connection(
    connection_id: int,
    current_user: CurrentUser,
    session: DBSession,
) -> ConnectionResponse:
    """Get a specific database connection."""
    can_access, _ = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    connection = await get_connection_by_id(session, connection_id)

    return ConnectionResponse(
        id=connection.id,
        name=connection.name,
        description=connection.description,
        host=connection.host,
        port=connection.port,
        database=connection.database,
        username=connection.username,
        ssl_mode=connection.ssl_mode,
        status=connection.status,
        status_message=connection.status_message,
        last_analyzed_at=connection.last_analyzed_at,
        analysis_progress=connection.analysis_progress,
        owner_id=connection.owner_id,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


@router.put("/{connection_id}", response_model=ConnectionResponse)
async def update_connection(
    connection_id: int,
    update_data: ConnectionUpdate,
    current_user: CurrentUser,
    session: DBSession,
) -> ConnectionResponse:
    """Update a database connection (owner or users with owner permission only)."""
    can_access, permission = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )
    
    connection = await get_connection_by_id(session, connection_id)
    # Only original owner or shared users with owner permission can update
    is_original_owner = connection.owner_id == current_user.id
    has_owner_permission = permission == SharePermission.OWNER
    
    if not is_original_owner and not has_owner_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this connection",
        )

    # Update fields
    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        if key == "password" and value:
            from app.connections.service import encrypt_password

            connection.encrypted_password = encrypt_password(value)
        elif hasattr(connection, key):
            setattr(connection, key, value)

    connection.updated_at = datetime.utcnow()
    session.add(connection)
    await session.commit()
    await session.refresh(connection)

    return ConnectionResponse(
        id=connection.id,
        name=connection.name,
        description=connection.description,
        host=connection.host,
        port=connection.port,
        database=connection.database,
        username=connection.username,
        ssl_mode=connection.ssl_mode,
        status=connection.status,
        status_message=connection.status_message,
        last_analyzed_at=connection.last_analyzed_at,
        analysis_progress=connection.analysis_progress,
        owner_id=connection.owner_id,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


@router.delete("/{connection_id}", response_model=MessageResponse)
async def remove_connection(
    connection_id: int,
    current_user: CurrentUser,
    session: DBSession,
) -> MessageResponse:
    """Delete a database connection (owner only)."""
    connection = await get_connection_by_id(session, connection_id)
    if not connection or connection.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    await delete_connection(session, connection)

    return MessageResponse(message="Connection deleted successfully")


@router.post("/{connection_id}/test", response_model=TestConnectionResult)
async def test_connection_endpoint(
    connection_id: int,
    current_user: CurrentUser,
    session: DBSession,
) -> TestConnectionResult:
    """Test connectivity to a database connection."""
    can_access, _ = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    connection = await get_connection_by_id(session, connection_id)
    password = decrypt_password(connection.encrypted_password)

    success, message, version = await test_connection(
        host=connection.host,
        port=connection.port,
        database=connection.database,
        username=connection.username,
        password=password,
        ssl_mode=connection.ssl_mode,
    )

    return TestConnectionResult(success=success, message=message, server_version=version)


@router.post("/{connection_id}/reanalyze", response_model=MessageResponse)
async def reanalyze_connection(
    connection_id: int,
    current_user: CurrentUser,
    session: DBSession,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    """Trigger re-analysis of a database connection."""
    can_access, permission = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )
    
    connection = await get_connection_by_id(session, connection_id)
    # Only original owner or shared users with owner permission can reanalyze
    is_original_owner = connection.owner_id == current_user.id
    has_owner_permission = permission == SharePermission.OWNER
    
    if not is_original_owner and not has_owner_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to re-analyze this connection",
        )

    if connection.status in [ConnectionStatus.ANALYZING, ConnectionStatus.INDEXING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Analysis is already in progress",
        )

    await update_connection_status(
        session, connection, ConnectionStatus.UPDATING, "Re-analysis queued", 0.0
    )

    background_tasks.add_task(trigger_analysis, connection.id)

    return MessageResponse(message="Re-analysis queued")


# =============================================================================
# Sharing Endpoints
# =============================================================================


@router.get("/{connection_id}/shares", response_model=ShareListResponse)
async def list_shares(
    connection_id: int,
    current_user: CurrentUser,
    session: DBSession,
) -> ShareListResponse:
    """List all shares for a connection."""
    can_access, _ = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    connection = await get_connection_by_id(session, connection_id)

    # Get owner info
    owner_stmt = select(User).where(User.id == connection.owner_id)
    owner_result = await session.execute(owner_stmt)
    owner = owner_result.scalar_one()

    # Get shares
    shares_stmt = (
        select(ConnectionShare, User)
        .join(User, User.id == ConnectionShare.user_id)
        .where(ConnectionShare.connection_id == connection_id)
    )
    shares_result = await session.execute(shares_stmt)

    shares = [
        ShareResponse(
            id=share.id,
            user_id=user.id,
            username=user.username,
            email=user.email,
            permission=share.permission,
            created_at=share.created_at,
        )
        for share, user in shares_result.all()
    ]

    return ShareListResponse(
        shares=shares,
        owner={"id": owner.id, "username": owner.username, "email": owner.email},
    )


@router.post("/{connection_id}/shares", response_model=ShareResponse)
async def add_share(
    connection_id: int,
    share_data: ShareCreate,
    current_user: CurrentUser,
    session: DBSession,
) -> ShareResponse:
    """Share a connection with another user (owner only)."""
    connection = await get_connection_by_id(session, connection_id)
    if not connection or connection.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    # Check if user exists
    user_stmt = select(User).where(User.id == share_data.user_id)
    user_result = await session.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found",
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot share with yourself",
        )

    share = await share_connection(session, connection, user.id, share_data.permission)

    return ShareResponse(
        id=share.id,
        user_id=user.id,
        username=user.username,
        email=user.email,
        permission=share.permission,
        created_at=share.created_at,
    )


@router.delete("/{connection_id}/shares/{user_id}", response_model=MessageResponse)
async def delete_share(
    connection_id: int,
    user_id: int,
    current_user: CurrentUser,
    session: DBSession,
) -> MessageResponse:
    """Remove a share from a connection (owner only)."""
    connection = await get_connection_by_id(session, connection_id)
    if not connection or connection.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    removed = await remove_share(session, connection_id, user_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share not found",
        )

    return MessageResponse(message="Share removed successfully")
