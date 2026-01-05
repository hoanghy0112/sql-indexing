"""
Agent Router

API endpoints for the chat agent.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import select

from app.agent.graph import run_agent
from app.agent.models import ChatMessage, ChatSession, MessageRole, SQLHistory
from app.auth.dependencies import CurrentUser, DBSession
from app.connections.service import (
    decrypt_password,
    get_connection_by_id,
    user_can_access_connection,
)
from app.rag.tools import set_connection_details

router = APIRouter()


class ChatRequest(BaseModel):
    """Request to chat with a database."""

    question: str = Field(..., min_length=1, max_length=2000)
    explain_mode: bool = Field(default=True)
    session_id: int | None = Field(default=None)


class ChatResponse(BaseModel):
    """Response from chat agent."""

    session_id: int
    message_id: int
    response: str
    sql: str | None
    explanation: str | None
    data: list | None
    columns: list[str] | None
    error: str | None


class ChatHistoryResponse(BaseModel):
    """Response for chat history."""

    session_id: int
    title: str | None
    messages: list[dict]
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    """Response for session list."""

    sessions: list[dict]


@router.post("/{connection_id}", response_model=ChatResponse)
async def chat_with_database(
    connection_id: int,
    request: ChatRequest,
    current_user: CurrentUser,
    session: DBSession,
) -> ChatResponse:
    """
    Chat with a database using natural language.

    - **explain_mode=True**: Returns JSON with sql, explanation, and data
    - **explain_mode=False**: Returns raw CSV data only
    """
    # Check access
    can_access, _ = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    # Get connection details
    connection = await get_connection_by_id(session, connection_id)
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    # Set connection details for tools
    password = decrypt_password(connection.encrypted_password)
    set_connection_details(connection_id, {
        "host": connection.host,
        "port": connection.port,
        "database": connection.database,
        "username": connection.username,
        "password": password,
        "ssl_mode": connection.ssl_mode,
    })

    # Get or create session
    if request.session_id:
        chat_session_stmt = select(ChatSession).where(
            ChatSession.id == request.session_id,
            ChatSession.connection_id == connection_id,
            ChatSession.user_id == current_user.id,
        )
        result = await session.execute(chat_session_stmt)
        chat_session = result.scalar_one_or_none()

        if not chat_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
    else:
        # Create new session
        chat_session = ChatSession(
            connection_id=connection_id,
            user_id=current_user.id,
            title=request.question[:100],
        )
        session.add(chat_session)
        await session.commit()
        await session.refresh(chat_session)

    # Save user message
    user_message = ChatMessage(
        session_id=chat_session.id,
        role=MessageRole.USER,
        content=request.question,
    )
    session.add(user_message)
    await session.commit()

    # Run agent
    try:
        result = await run_agent(
            question=request.question,
            connection_id=connection_id,
            explain_mode=request.explain_mode,
        )

        # Save assistant message
        assistant_message = ChatMessage(
            session_id=chat_session.id,
            role=MessageRole.ASSISTANT,
            content=result.get("response", ""),
            sql_query=result.get("sql"),
            explanation=result.get("explanation"),
            data_json=json.dumps(result.get("data")) if result.get("data") else None,
        )
        session.add(assistant_message)

        # Save SQL history if query was executed
        if result.get("sql"):
            sql_history = SQLHistory(
                connection_id=connection_id,
                user_id=current_user.id,
                query=result["sql"],
                row_count=len(result.get("data", [])) if result.get("data") else None,
                error=result.get("error"),
            )
            session.add(sql_history)

        # Update session timestamp
        chat_session.updated_at = datetime.now(timezone.utc)
        session.add(chat_session)

        await session.commit()
        await session.refresh(assistant_message)

        return ChatResponse(
            session_id=chat_session.id,
            message_id=assistant_message.id,
            response=result.get("response", ""),
            sql=result.get("sql"),
            explanation=result.get("explanation"),
            data=result.get("data"),
            columns=result.get("columns"),
            error=result.get("error"),
        )

    except Exception as e:
        # Save error message
        error_message = ChatMessage(
            session_id=chat_session.id,
            role=MessageRole.ASSISTANT,
            content=f"Error: {str(e)}",
        )
        session.add(error_message)
        await session.commit()
        await session.refresh(error_message)

        return ChatResponse(
            session_id=chat_session.id,
            message_id=error_message.id,
            response=f"Error processing your question: {str(e)}",
            sql=None,
            explanation=None,
            data=None,
            columns=None,
            error=str(e),
        )


@router.get("/{connection_id}/sessions", response_model=SessionListResponse)
async def list_sessions(
    connection_id: int,
    current_user: CurrentUser,
    session: DBSession,
) -> SessionListResponse:
    """List all chat sessions for a connection."""
    can_access, _ = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    stmt = (
        select(ChatSession)
        .where(
            ChatSession.connection_id == connection_id,
            ChatSession.user_id == current_user.id,
        )
        .order_by(ChatSession.updated_at.desc())
    )

    result = await session.execute(stmt)
    sessions = result.scalars().all()

    return SessionListResponse(
        sessions=[
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ]
    )


@router.get("/{connection_id}/sessions/{session_id}", response_model=ChatHistoryResponse)
async def get_session_history(
    connection_id: int,
    session_id: int,
    current_user: CurrentUser,
    session: DBSession,
) -> ChatHistoryResponse:
    """Get chat history for a session."""
    # Check access
    can_access, _ = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    # Get session
    stmt = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.connection_id == connection_id,
        ChatSession.user_id == current_user.id,
    )
    result = await session.execute(stmt)
    chat_session = result.scalar_one_or_none()

    if not chat_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Get messages
    msg_stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    msg_result = await session.execute(msg_stmt)
    messages = msg_result.scalars().all()

    return ChatHistoryResponse(
        session_id=chat_session.id,
        title=chat_session.title,
        messages=[
            {
                "id": m.id,
                "role": m.role.value,
                "content": m.content,
                "sql": m.sql_query,
                "explanation": m.explanation,
                "data": json.loads(m.data_json) if m.data_json else None,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        created_at=chat_session.created_at,
        updated_at=chat_session.updated_at,
    )


@router.delete("/{connection_id}/sessions/{session_id}")
async def delete_session(
    connection_id: int,
    session_id: int,
    current_user: CurrentUser,
    session: DBSession,
):
    """Delete a chat session."""
    # Check access
    can_access, _ = await user_can_access_connection(session, current_user, connection_id)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    # Get session
    stmt = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.connection_id == connection_id,
        ChatSession.user_id == current_user.id,
    )
    result = await session.execute(stmt)
    chat_session = result.scalar_one_or_none()

    if not chat_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Delete messages first
    msg_stmt = select(ChatMessage).where(ChatMessage.session_id == session_id)
    msg_result = await session.execute(msg_stmt)
    for msg in msg_result.scalars().all():
        await session.delete(msg)

    # Delete session
    await session.delete(chat_session)
    await session.commit()

    return {"message": "Session deleted successfully"}
