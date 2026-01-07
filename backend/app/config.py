"""
Database RAG & Analytics Platform - Configuration

Centralized configuration management using Pydantic Settings.
All configuration is loaded from environment variables.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==========================================================================
    # Application Settings
    # ==========================================================================
    app_name: str = "Database RAG & Analytics Platform"
    app_version: str = "0.1.0"
    debug: bool = Field(default=False, alias="BACKEND_DEBUG")
    environment: Literal["development", "staging", "production"] = "development"

    # ==========================================================================
    # Database Settings (System PostgreSQL)
    # ==========================================================================
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://sqlindex:sqlindex_secret@localhost:5432/sqlindex_system",
        alias="DATABASE_URL",
    )

    # ==========================================================================
    # Redis Settings
    # ==========================================================================
    redis_url: RedisDsn = Field(
        default="redis://localhost:6379",
        alias="REDIS_URL",
    )

    # ==========================================================================
    # Qdrant Vector Database Settings
    # ==========================================================================
    qdrant_host: str = Field(default="localhost", alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, alias="QDRANT_PORT")
    qdrant_collection_name: str = "database_insights"

    # ==========================================================================
    # Ollama LLM Settings
    # ==========================================================================
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:3b", alias="OLLAMA_MODEL")

    # ==========================================================================
    # Embedding Model Settings
    # ==========================================================================
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="EMBEDDING_MODEL",
    )
    embedding_model_path: str | None = Field(default=None, alias="EMBEDDING_MODEL_PATH")

    # ==========================================================================
    # JWT Authentication Settings
    # ==========================================================================
    jwt_secret: str = Field(
        default="your-super-secret-jwt-key-change-in-production",
        alias="JWT_SECRET",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=1440, alias="JWT_EXPIRE_MINUTES")  # 24 hours

    # ==========================================================================
    # Analysis Configuration
    # ==========================================================================
    category_threshold: int = Field(
        default=100,
        alias="CATEGORY_THRESHOLD",
        description="Max distinct values before column is considered 'random text' vs 'category'",
    )
    sample_size: int = Field(
        default=50,
        alias="SAMPLE_SIZE",
        description="Number of sample rows to fetch for high-cardinality columns",
    )
    reanalysis_interval_hours: int = Field(
        default=168,
        alias="REANALYSIS_INTERVAL_HOURS",
        description="Periodic re-analysis interval (default: 1 week = 168 hours)",
    )

    # ==========================================================================
    # CORS Settings
    # ==========================================================================
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        alias="CORS_ORIGINS",
    )

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL (for Alembic migrations)."""
        return str(self.database_url).replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
