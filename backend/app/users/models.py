"""
User Models

SQLModel entities for user management.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.connections.models import DatabaseConnection, ConnectionShare


class User(SQLModel, table=True):
    """User entity for authentication and authorization."""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=50)
    email: str = Field(unique=True, index=True, max_length=255)
    hashed_password: str = Field(max_length=255)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = Field(default_factory=lambda: datetime.utcnow())

    # Relationships
    connections: list["DatabaseConnection"] = Relationship(back_populates="owner")
    shared_connections: list["ConnectionShare"] = Relationship(back_populates="user")
