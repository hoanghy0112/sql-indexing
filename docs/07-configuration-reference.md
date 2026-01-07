# Configuration Reference

This document provides a complete reference for all configuration options in the application.

---

## Environment Variables

All configuration is managed through environment variables. Copy `.env.example` to `.env` and configure as needed.

---

## System PostgreSQL Database

The system database stores users, connections, insights, and chat history.

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `POSTGRES_USER` | Database username | `sqlindex` | Yes |
| `POSTGRES_PASSWORD` | Database password | - | Yes |
| `POSTGRES_DB` | Database name | `sqlindex_system` | Yes |
| `POSTGRES_PORT` | External port mapping | `5432` | No |
| `DATABASE_URL` | Full connection string (auto-generated) | - | No |

**Example**:
```bash
POSTGRES_USER=sqlindex
POSTGRES_PASSWORD=super_secret_password
POSTGRES_DB=sqlindex_system
POSTGRES_PORT=5433
```

---

## Qdrant Vector Database

Stores embeddings for semantic search.

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `QDRANT_HOST` | Qdrant hostname | `localhost` | No |
| `QDRANT_PORT` | Qdrant HTTP port | `6333` | No |
| `QDRANT_HTTP_PORT` | External HTTP port mapping | `6333` | No |
| `QDRANT_GRPC_PORT` | External gRPC port mapping | `6334` | No |

**Collection Configuration** (in `config.py`):
```python
qdrant_collection_name: str = "database_insights"
```

---

## Kafka & Zookeeper

Message queue for async processing (prepared for future use).

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `ZOOKEEPER_PORT` | Zookeeper client port | `2181` | No |
| `KAFKA_PORT` | Kafka broker port | `29092` | No |

---

## Redis

Cache and session storage.

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `REDIS_PORT` | Redis port | `6379` | No |
| `REDIS_URL` | Full connection URL | `redis://localhost:6379` | No |

---

## Ollama LLM Server

Local LLM for intelligent features.

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `OLLAMA_PORT` | Ollama API port | `11434` | No |
| `OLLAMA_BASE_URL` | Full Ollama URL | `http://localhost:11434` | No |
| `OLLAMA_MODEL` | Model name | `qwen2.5:3b` | No |

**Supported Models**:
- `qwen2.5:3b` (default, balanced)
- `qwen3:4b` (more capable)
- `llama3:8b` (larger, slower)
- `mistral:7b` (good general purpose)

**Pull model**:
```bash
make ollama-pull
# Or manually:
docker compose exec ollama ollama pull qwen2.5:3b
```

---

## JWT Authentication

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `JWT_SECRET` | Secret key for signing | - | **Yes (production)** |
| `JWT_ALGORITHM` | Signing algorithm | `HS256` | No |
| `JWT_EXPIRE_MINUTES` | Token expiration (minutes) | `1440` (24h) | No |

> [!CAUTION]
> Always set a strong, unique `JWT_SECRET` in production!

**Example**:
```bash
JWT_SECRET=your-super-secret-key-at-least-32-characters-long
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
```

---

## Backend API

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `BACKEND_PORT` | API server port | `8000` | No |
| `BACKEND_DEBUG` | Enable debug mode | `false` | No |

**Debug mode enables**:
- SQL query logging
- Detailed error messages
- Hot reload
- Verbose tracebacks

---

## Frontend

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `FRONTEND_PORT` | Frontend server port | `3000` | No |
| `NEXT_PUBLIC_API_URL` | Backend API URL | `http://localhost:8000` | Yes |

> [!IMPORTANT]
> `NEXT_PUBLIC_API_URL` must be accessible from the browser, not just the server.

---

## Embedding Model

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `EMBEDDING_MODEL` | HuggingFace model name | `sentence-transformers/all-MiniLM-L6-v2` | No |
| `EMBEDDING_MODEL_PATH` | Local model path | - | No |

**Supported Models**:

| Model | Dimensions | Notes |
|-------|------------|-------|
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | Fast, lightweight (default) |
| `sentence-transformers/all-mpnet-base-v2` | 768 | Higher quality |
| `BAAI/bge-small-en` | 384 | Good for retrieval |
| `BAAI/bge-base-en` | 768 | Better quality |

> [!WARNING]
> Changing the embedding model requires re-analyzing all connections to regenerate embeddings.

---

## Analysis Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `CATEGORY_THRESHOLD` | Max distinct values for categorical indexing | `100` | No |
| `SAMPLE_SIZE` | Sample rows for high-cardinality columns | `50` | No |
| `REANALYSIS_INTERVAL_HOURS` | Auto re-analysis interval | `168` (1 week) | No |

**Indexing Strategy Logic**:

```
IF distinct_count <= CATEGORY_THRESHOLD:
    strategy = CATEGORICAL (store all values)
ELSE IF column is text type:
    strategy = VECTOR (embed for semantic search)
ELSE:
    strategy = SKIP (IDs, timestamps, etc.)
```

---

## CORS Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `CORS_ORIGINS` | Allowed origins (JSON array) | `["http://localhost:3000", "http://localhost:8000"]` | No |

**Example**:
```bash
CORS_ORIGINS=["http://localhost:3000", "https://app.example.com"]
```

---

## Complete .env Example

```bash
# =============================================================================
# Database RAG & Analytics Platform - Environment Configuration
# =============================================================================

# -----------------------------------------------------------------------------
# System PostgreSQL Database
# -----------------------------------------------------------------------------
POSTGRES_USER=sqlindex
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=sqlindex_system
POSTGRES_PORT=5433

# -----------------------------------------------------------------------------
# Qdrant Vector Database
# -----------------------------------------------------------------------------
QDRANT_HTTP_PORT=6333
QDRANT_GRPC_PORT=6334

# -----------------------------------------------------------------------------
# Kafka & Zookeeper
# -----------------------------------------------------------------------------
ZOOKEEPER_PORT=2181
KAFKA_PORT=29092

# -----------------------------------------------------------------------------
# Redis
# -----------------------------------------------------------------------------
REDIS_PORT=6379

# -----------------------------------------------------------------------------
# Ollama LLM Server
# -----------------------------------------------------------------------------
OLLAMA_PORT=11434
OLLAMA_MODEL=qwen2.5:3b

# -----------------------------------------------------------------------------
# JWT Authentication
# IMPORTANT: Change in production!
# -----------------------------------------------------------------------------
JWT_SECRET=change-this-to-a-very-long-random-string-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# -----------------------------------------------------------------------------
# Backend API
# -----------------------------------------------------------------------------
BACKEND_PORT=8000
BACKEND_DEBUG=true

# -----------------------------------------------------------------------------
# Frontend
# -----------------------------------------------------------------------------
FRONTEND_PORT=3000
NEXT_PUBLIC_API_URL=http://localhost:8000

# -----------------------------------------------------------------------------
# Embedding Model
# -----------------------------------------------------------------------------
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# -----------------------------------------------------------------------------
# Analysis Configuration
# -----------------------------------------------------------------------------
CATEGORY_THRESHOLD=100
SAMPLE_SIZE=50
REANALYSIS_INTERVAL_HOURS=168
```

---

## Configuration in Code

Configuration is accessed through the `Settings` class:

```python
from app.config import get_settings

settings = get_settings()

# Access settings
print(settings.ollama_model)
print(settings.jwt_secret)
print(settings.category_threshold)
```

The `get_settings()` function is cached using `@lru_cache`, so the settings are loaded only once.

---

## Docker Compose Override

For local development, you can override settings with `docker-compose.override.yml`:

```yaml
version: '3.8'

services:
  backend:
    environment:
      - BACKEND_DEBUG=true
    ports:
      - "8001:8000"  # Different port
    
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

---

## Production Considerations

### Security

1. **Use strong secrets**:
   ```bash
   JWT_SECRET=$(openssl rand -base64 48)
   POSTGRES_PASSWORD=$(openssl rand -base64 32)
   ```

2. **Disable debug mode**:
   ```bash
   BACKEND_DEBUG=false
   ```

3. **Restrict CORS**:
   ```bash
   CORS_ORIGINS=["https://your-domain.com"]
   ```

### Performance

1. **Use larger embedding model** for better results:
   ```bash
   EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
   ```

2. **Tune connection pool**:
   ```python
   # In database.py
   engine = create_async_engine(
       pool_size=20,
       max_overflow=40,
   )
   ```

3. **Enable Redis caching** (future enhancement).

### Monitoring

1. **Health checks**: `/health` endpoint
2. **Prometheus metrics**: (future enhancement)
3. **Logging**: Configure structured logging for production
