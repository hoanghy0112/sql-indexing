"""
Users Router

API endpoints for user management.
"""

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.auth.dependencies import CurrentUser, DBSession
from app.auth.schemas import UserResponse, MessageResponse
from app.auth.service import get_password_hash, verify_password
from app.users.models import User
from pydantic import BaseModel, Field


router = APIRouter()


class UpdateProfile(BaseModel):
    """Schema for updating user profile."""

    email: str | None = None


class ChangePassword(BaseModel):
    """Schema for changing password."""

    current_password: str
    new_password: str = Field(min_length=8, max_length=100)


class UserListResponse(BaseModel):
    """Schema for user list response (for sharing)."""

    id: int
    username: str
    email: str


@router.get("/me", response_model=UserResponse)
async def get_profile(current_user: CurrentUser) -> UserResponse:
    """Get current user profile."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat(),
    )


@router.put("/me", response_model=UserResponse)
async def update_profile(
    profile_data: UpdateProfile,
    current_user: CurrentUser,
    session: DBSession,
) -> UserResponse:
    """Update current user profile."""
    if profile_data.email:
        # Check if email is already taken
        statement = select(User).where(
            User.email == profile_data.email, User.id != current_user.id
        )
        result = await session.execute(statement)
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use",
            )
        current_user.email = profile_data.email

    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)

    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat(),
    )


@router.post("/me/change-password", response_model=MessageResponse)
async def change_password(
    password_data: ChangePassword,
    current_user: CurrentUser,
    session: DBSession,
) -> MessageResponse:
    """Change current user password."""
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.hashed_password = get_password_hash(password_data.new_password)
    session.add(current_user)
    await session.commit()

    return MessageResponse(message="Password changed successfully")


@router.get("/search", response_model=list[UserListResponse])
async def search_users(
    q: str,
    current_user: CurrentUser,
    session: DBSession,
) -> list[UserListResponse]:
    """
    Search for users by username or email (for sharing databases).
    Excludes the current user from results.
    """
    if len(q) < 2:
        return []

    statement = select(User).where(
        User.id != current_user.id,
        User.is_active == True,  # noqa: E712
        (User.username.ilike(f"%{q}%")) | (User.email.ilike(f"%{q}%")),
    ).limit(10)

    result = await session.execute(statement)
    users = result.scalars().all()

    return [
        UserListResponse(id=user.id, username=user.username, email=user.email)
        for user in users
    ]
