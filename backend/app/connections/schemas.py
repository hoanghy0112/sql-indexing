"""
Database Connection Schemas

Pydantic models for connection requests and responses.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class ConnectionStatus(str, Enum):
    """Status of a database connection."""

    PENDING = "pending"
    ANALYZING = "analyzing"
    INDEXING = "indexing"
    READY = "ready"
    ERROR = "error"
    UPDATING = "updating"


class SharePermission(str, Enum):
    """Permission level for shared connections."""

    CHAT = "chat"
    VIEW = "view"
    OWNER = "owner"


class ConnectionCreate(BaseModel):
    """Schema for creating a new database connection."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(..., min_length=1, max_length=100)
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)
    ssl_mode: str = Field(default="prefer")

    @field_validator("ssl_mode")
    @classmethod
    def validate_ssl_mode(cls, v: str) -> str:
        valid_modes = ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]
        if v not in valid_modes:
            raise ValueError(f"ssl_mode must be one of: {valid_modes}")
        return v


class ConnectionFromURL(BaseModel):
    """Schema for creating a connection from a URL."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    connection_url: str = Field(..., min_length=1)


class ConnectionUpdate(BaseModel):
    """Schema for updating a connection."""

    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, max_length=100)
    username: str | None = Field(default=None, max_length=100)
    password: str | None = None
    ssl_mode: str | None = None


class ConnectionResponse(BaseModel):
    """Schema for connection response."""

    id: int
    name: str
    description: str | None
    host: str
    port: int
    database: str
    username: str
    ssl_mode: str
    status: ConnectionStatus
    status_message: str | None
    last_analyzed_at: datetime | None
    analysis_progress: float
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConnectionListResponse(BaseModel):
    """Schema for connection list item."""

    id: int
    name: str
    description: str | None
    database: str
    status: ConnectionStatus
    analysis_progress: float
    last_analyzed_at: datetime | None
    is_owner: bool
    permission: SharePermission | None  # None for owner


class ShareCreate(BaseModel):
    """Schema for sharing a connection."""

    user_id: int
    permission: SharePermission = SharePermission.VIEW


class ShareResponse(BaseModel):
    """Schema for share response."""

    id: int
    user_id: int
    username: str
    email: str
    permission: SharePermission
    created_at: datetime


class ShareListResponse(BaseModel):
    """Schema for list of shares."""

    shares: list[ShareResponse]
    owner: dict  # { id, username, email }


class TestConnectionResult(BaseModel):
    """Schema for connection test result."""

    success: bool
    message: str
    server_version: str | None = None
