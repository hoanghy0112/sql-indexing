"""
Database Connection Models

SQLModel entities for managing external database connections.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.users.models import User


class ConnectionStatus(str, Enum):
    """Status of a database connection."""

    PENDING = "pending"  # Just added, not yet analyzed
    ANALYZING = "analyzing"  # Currently being analyzed
    INDEXING = "indexing"  # Insights being indexed to vector store
    READY = "ready"  # Ready for queries
    ERROR = "error"  # Error during analysis/indexing
    UPDATING = "updating"  # Re-analysis in progress


class SharePermission(str, Enum):
    """Permission level for shared connections."""

    CHAT = "chat"  # Only Ask DB tab (General + Chat)
    VIEW = "view"  # Ask DB + Intelligence tabs (General + Chat + Intelligence)
    OWNER = "owner"  # Full access including Settings


class DatabaseConnection(SQLModel, table=True):
    """External database connection entity."""

    __tablename__ = "database_connections"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    description: str | None = Field(default=None, max_length=500)

    # Connection details (encrypted in production)
    host: str = Field(max_length=255)
    port: int = Field(default=5432)
    database: str = Field(max_length=100)
    username: str = Field(max_length=100)
    encrypted_password: str = Field(max_length=500)  # Encrypted password

    # SSL Configuration
    ssl_mode: str = Field(default="prefer", max_length=20)

    # Status tracking
    status: ConnectionStatus = Field(default=ConnectionStatus.PENDING)
    status_message: str | None = Field(default=None, max_length=500)
    last_analyzed_at: datetime | None = Field(default=None)
    analysis_progress: float = Field(default=0.0)  # 0-100 percentage

    # Metadata
    owner_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    owner: "User" = Relationship(back_populates="connections")
    shares: list["ConnectionShare"] = Relationship(back_populates="connection")
    insights: list["TableInsight"] = Relationship(back_populates="connection")


class ConnectionShare(SQLModel, table=True):
    """Sharing a database connection with another user."""

    __tablename__ = "connection_shares"

    id: int | None = Field(default=None, primary_key=True)
    connection_id: int = Field(foreign_key="database_connections.id")
    user_id: int = Field(foreign_key="users.id")
    permission: SharePermission = Field(default=SharePermission.VIEW)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    connection: DatabaseConnection = Relationship(back_populates="shares")
    user: "User" = Relationship(back_populates="shared_connections")


class IndexingStrategy(str, Enum):
    """Indexing strategy for columns."""

    CATEGORICAL = "categorical"  # Low cardinality - store values in metadata
    VECTOR = "vector"  # High cardinality - vector index for search
    SKIP = "skip"  # Not indexed (e.g., IDs, timestamps)


class TableInsight(SQLModel, table=True):
    """Insights and metadata for a database table."""

    __tablename__ = "table_insights"

    id: int | None = Field(default=None, primary_key=True)
    connection_id: int = Field(foreign_key="database_connections.id")

    # Table info
    schema_name: str = Field(default="public", max_length=100)
    table_name: str = Field(max_length=100)
    row_count: int = Field(default=0)

    # Generated insights
    summary: str | None = Field(default=None)  # AI-generated summary
    insight_document: str | None = Field(default=None)  # Full document for vectorization

    # Vector store reference
    vector_id: str | None = Field(default=None, max_length=100)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    connection: DatabaseConnection = Relationship(back_populates="insights")
    columns: list["ColumnMetadata"] = Relationship(back_populates="table_insight")


class ColumnMetadata(SQLModel, table=True):
    """Metadata for a database column."""

    __tablename__ = "column_metadata"

    id: int | None = Field(default=None, primary_key=True)
    table_insight_id: int = Field(foreign_key="table_insights.id")

    # Column info
    column_name: str = Field(max_length=100)
    data_type: str = Field(max_length=100)
    is_nullable: bool = Field(default=True)
    is_primary_key: bool = Field(default=False)
    is_foreign_key: bool = Field(default=False)
    foreign_key_ref: str | None = Field(default=None, max_length=200)

    # Statistics
    distinct_count: int | None = Field(default=None)
    null_count: int | None = Field(default=None)

    # Indexing decision
    indexing_strategy: IndexingStrategy = Field(default=IndexingStrategy.SKIP)

    # For CATEGORICAL columns: store all possible values
    categorical_values: str | None = Field(default=None)  # JSON array

    # For VECTOR columns: sample values
    sample_values: str | None = Field(default=None)  # JSON array

    # AI-generated summary for this column
    column_summary: str | None = Field(default=None)

    # Relationships
    table_insight: TableInsight = Relationship(back_populates="columns")
