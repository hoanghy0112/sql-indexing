"""
Chat Models

SQLModel entities for chat history and sessions.
"""

from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class MessageRole(str, Enum):
    """Role of a chat message."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatSession(SQLModel, table=True):
    """Chat session for a database connection."""

    __tablename__ = "chat_sessions"

    id: int | None = Field(default=None, primary_key=True)
    connection_id: int = Field(foreign_key="database_connections.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    title: str | None = Field(default=None, max_length=200)
    
    # Public sharing
    is_public: bool = Field(default=False)
    share_token: str | None = Field(default=None, max_length=64, index=True)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(SQLModel, table=True):
    """Individual chat message."""

    __tablename__ = "chat_messages"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="chat_sessions.id", index=True)
    role: MessageRole
    content: str
    
    # For assistant responses with explain_mode
    sql_query: str | None = Field(default=None)
    explanation: str | None = Field(default=None)
    data_json: str | None = Field(default=None)  # JSON serialized result data
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SQLHistory(SQLModel, table=True):
    """History of SQL queries executed."""

    __tablename__ = "sql_history"

    id: int | None = Field(default=None, primary_key=True)
    connection_id: int = Field(foreign_key="database_connections.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    query: str
    execution_time_ms: int | None = Field(default=None)
    row_count: int | None = Field(default=None)
    error: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
