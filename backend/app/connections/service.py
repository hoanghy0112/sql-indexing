"""
Database Connection Service

Business logic for managing external database connections.
"""

import asyncio
import base64
from urllib.parse import urlparse

import asyncpg
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_settings
from app.connections.models import (
    ConnectionShare,
    ConnectionStatus,
    DatabaseConnection,
    SharePermission,
)
from app.users.models import User

settings = get_settings()

# In production, use a proper key management system

# Derive stable key from JWT_SECRET
# Ensure 32 bytes and URL-safe base64 encoding
key_bytes = settings.jwt_secret.encode()[:32].ljust(32, b"0")
stable_key = base64.urlsafe_b64encode(key_bytes)

# Initialize Fernet with stable key
fernet = Fernet(stable_key)


def encrypt_password(password: str) -> str:
    """Encrypt a password for storage."""
    return fernet.encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """Decrypt a stored password."""
    return fernet.decrypt(encrypted.encode()).decode()


def parse_connection_url(url: str) -> dict:
    """Parse a PostgreSQL connection URL into components."""
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/") if parsed.path else "",
        "username": parsed.username or "",
        "password": parsed.password or "",
    }


async def test_connection(
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    ssl_mode: str = "prefer",
) -> tuple[bool, str, str | None]:
    """
    Test a PostgreSQL connection.
    Returns (success, message, server_version).
    """
    ssl_map = {
        "disable": False,
        "allow": "prefer",
        "prefer": "prefer",
        "require": True,
        "verify-ca": True,
        "verify-full": True,
    }

    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=host,
                port=port,
                database=database,
                user=username,
                password=password,
                ssl=ssl_map.get(ssl_mode, "prefer"),
            ),
            timeout=10.0,
        )

        version = await conn.fetchval("SELECT version()")
        await conn.close()

        return True, "Connection successful", version

    except asyncio.TimeoutError:
        return False, "Connection timed out", None
    except asyncpg.InvalidPasswordError:
        return False, "Invalid password", None
    except asyncpg.InvalidCatalogNameError:
        return False, f"Database '{database}' does not exist", None
    except OSError as e:
        return False, f"Network error: {e}", None
    except Exception as e:
        return False, f"Connection failed: {str(e)}", None


async def create_connection(
    session: AsyncSession,
    owner: User,
    name: str,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    description: str | None = None,
    ssl_mode: str = "prefer",
) -> DatabaseConnection:
    """Create a new database connection."""
    connection = DatabaseConnection(
        name=name,
        description=description,
        host=host,
        port=port,
        database=database,
        username=username,
        encrypted_password=encrypt_password(password),
        ssl_mode=ssl_mode,
        owner_id=owner.id,
        status=ConnectionStatus.PENDING,
    )

    session.add(connection)
    await session.commit()
    await session.refresh(connection)

    return connection


async def get_connection_by_id(
    session: AsyncSession, connection_id: int
) -> DatabaseConnection | None:
    """Get a connection by ID."""
    statement = select(DatabaseConnection).where(DatabaseConnection.id == connection_id)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def get_user_connections(
    session: AsyncSession, user: User
) -> list[tuple[DatabaseConnection, bool, SharePermission | None]]:
    """
    Get all connections accessible by a user (owned + shared).
    Returns list of (connection, is_owner, permission) tuples.
    Permission is None for owner (has all permissions).
    """
    # Get owned connections
    owned_stmt = select(DatabaseConnection).where(DatabaseConnection.owner_id == user.id)
    owned_result = await session.execute(owned_stmt)
    owned = [(conn, True, None) for conn in owned_result.scalars().all()]

    # Get shared connections
    shared_stmt = (
        select(DatabaseConnection, ConnectionShare)
        .join(ConnectionShare, ConnectionShare.connection_id == DatabaseConnection.id)
        .where(ConnectionShare.user_id == user.id)
    )
    shared_result = await session.execute(shared_stmt)
    shared = [(conn, False, share.permission) for conn, share in shared_result.all()]

    return owned + shared


async def user_can_access_connection(
    session: AsyncSession, user: User, connection_id: int
) -> tuple[bool, SharePermission | None]:
    """
    Check if user can access a connection.
    Returns (can_access, permission).
    Permission is None for owner (has all permissions).
    """
    connection = await get_connection_by_id(session, connection_id)
    if not connection:
        return False, None

    # Owner has full access
    if connection.owner_id == user.id:
        return True, None  # None means owner (full access)

    # Check shares
    share_stmt = select(ConnectionShare).where(
        ConnectionShare.connection_id == connection_id,
        ConnectionShare.user_id == user.id,
    )
    result = await session.execute(share_stmt)
    share = result.scalar_one_or_none()

    if share:
        return True, share.permission

    return False, None


async def share_connection(
    session: AsyncSession,
    connection: DatabaseConnection,
    user_id: int,
    permission: SharePermission = SharePermission.VIEW,
) -> ConnectionShare:
    """Share a connection with another user."""
    # Check if already shared
    existing_stmt = select(ConnectionShare).where(
        ConnectionShare.connection_id == connection.id,
        ConnectionShare.user_id == user_id,
    )
    result = await session.execute(existing_stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.permission = permission
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing

    share = ConnectionShare(
        connection_id=connection.id,
        user_id=user_id,
        permission=permission,
    )
    session.add(share)
    await session.commit()
    await session.refresh(share)

    return share


async def remove_share(
    session: AsyncSession, connection_id: int, user_id: int
) -> bool:
    """Remove a share."""
    stmt = select(ConnectionShare).where(
        ConnectionShare.connection_id == connection_id,
        ConnectionShare.user_id == user_id,
    )
    result = await session.execute(stmt)
    share = result.scalar_one_or_none()

    if not share:
        return False

    await session.delete(share)
    await session.commit()
    return True


async def update_connection_status(
    session: AsyncSession,
    connection: DatabaseConnection,
    status: ConnectionStatus,
    message: str | None = None,
    progress: float | None = None,
) -> None:
    """Update connection analysis status."""
    connection.status = status
    if message is not None:
        connection.status_message = message
    if progress is not None:
        connection.analysis_progress = progress

    session.add(connection)
    await session.commit()


async def delete_connection(session: AsyncSession, connection: DatabaseConnection) -> None:
    """Delete a connection and all related data."""
    # Delete shares
    shares_stmt = select(ConnectionShare).where(
        ConnectionShare.connection_id == connection.id
    )
    shares_result = await session.execute(shares_stmt)
    for share in shares_result.scalars().all():
        await session.delete(share)

    # Delete the connection (cascade should handle insights/columns)
    await session.delete(connection)
    await session.commit()
