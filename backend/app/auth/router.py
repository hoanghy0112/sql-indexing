"""
Authentication Router

API endpoints for user registration, login, and authentication.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.auth.schemas import (
    MessageResponse,
    Token,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.auth.service import (
    authenticate_user,
    create_access_token,
    create_user,
    get_user_by_email,
    get_user_by_username,
)
from app.auth.dependencies import CurrentUser

settings = get_settings()
router = APIRouter()


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MessageResponse:
    """
    Register a new user.

    - **username**: Unique username (3-50 characters, alphanumeric and underscores only)
    - **email**: Valid email address
    - **password**: Password (minimum 8 characters)
    """
    # Check if username already exists
    existing_user = await get_user_by_username(session, user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Check if email already exists
    existing_email = await get_user_by_email(session, user_data.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    await create_user(
        session,
        username=user_data.username,
        email=user_data.email,
        password=user_data.password,
    )

    return MessageResponse(message="User registered successfully")


@router.post("/login", response_model=Token)
async def login(
    user_data: UserLogin,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Token:
    """
    Authenticate user and return JWT token.

    - **username**: User's username
    - **password**: User's password
    """
    user = await authenticate_user(session, user_data.username, user_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.jwt_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.id, "username": user.username},
        expires_delta=access_token_expires,
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUser) -> UserResponse:
    """Get current authenticated user information."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat(),
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(current_user: CurrentUser) -> Token:
    """Refresh the JWT token for the current user."""
    access_token_expires = timedelta(minutes=settings.jwt_expire_minutes)
    access_token = create_access_token(
        data={"sub": current_user.id, "username": current_user.username},
        expires_delta=access_token_expires,
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
    )
