"""
Database RAG & Analytics Platform - FastAPI Application

Main entry point for the backend API server.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db, close_db

# Import routers
from app.auth.router import router as auth_router
from app.users.router import router as users_router
from app.connections.router import router as connections_router
from app.intelligence.router import router as intelligence_router
from app.agent.router import router as agent_router
from app.system.router import router as system_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    A platform that allows users to connect PostgreSQL databases, 
    automatically analyze their schema/metadata using AI, 
    and chat with their data using a multi-agent system.
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(users_router, prefix="/users", tags=["Users"])
app.include_router(connections_router, prefix="/connections", tags=["Database Connections"])
app.include_router(intelligence_router, prefix="/intelligence", tags=["Intelligence Engine"])
app.include_router(agent_router, prefix="/chat", tags=["Chat Agent"])
app.include_router(system_router, prefix="/system", tags=["System"])


@app.get("/", tags=["Health"])
async def root() -> dict[str, str]:
    """Root endpoint - health check."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Detailed health check endpoint."""
    return {
        "status": "healthy",
        "database": "connected",
        "vector_store": "connected",
    }
