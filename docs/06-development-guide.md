# Development Guide

This document provides guidelines and best practices for developing and extending the Database RAG & Analytics Platform.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Workflow](#development-workflow)
3. [Project Conventions](#project-conventions)
4. [Adding New Features](#adding-new-features)
5. [Testing](#testing)
6. [Debugging](#debugging)
7. [Common Issues](#common-issues)

---

## Getting Started

### Prerequisites

- **Docker & Docker Compose** - For infrastructure services
- **Python 3.11+** - Backend runtime
- **Poetry** - Python dependency management
- **Node.js 18+** - Frontend runtime
- **pnpm/npm** - Node.js package manager

### Initial Setup

```bash
# Clone the repository
git clone <repository-url>
cd sql-indexing

# Copy environment file
cp .env.example .env
# Edit .env with your configurations

# Install all dependencies
make setup

# Start development environment
make dev

# In a separate terminal, pull the LLM model (first time only)
make ollama-pull
```

### Verify Installation

1. **Frontend**: http://localhost:3000
2. **Backend API**: http://localhost:8000
3. **API Docs**: http://localhost:8000/docs
4. **Qdrant Dashboard**: http://localhost:6333/dashboard

---

## Development Workflow

### Starting Services

```bash
# Full development environment (recommended)
make dev

# Or start services separately:
make dev-backend    # Backend with hot reload
make dev-frontend   # Frontend with hot reload

# Docker-based (no hot reload)
make dev-docker
```

### Stopping Services

```bash
make stop           # Stop all Docker containers
# Ctrl+C             # Stop local dev servers
```

### Viewing Logs

```bash
make logs           # All services
make logs-backend   # Backend only
make logs-frontend  # Frontend only
```

### Database Migrations

```bash
# Run migrations
make migrate

# Create new migration
make migrate-create name=add_new_column

# Rollback last migration
make migrate-rollback
```

---

## Project Conventions

### Backend (Python)

#### File Organization

Each module follows this structure:

```
module/
├── __init__.py       # Exports
├── router.py         # FastAPI router with endpoints
├── service.py        # Business logic
├── models.py         # SQLModel entities
├── schemas.py        # Pydantic schemas
└── dependencies.py   # FastAPI dependencies
```

#### Naming Conventions

- **Files**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`
- **Variables**: `snake_case`

#### Type Hints

Always use type hints:

```python
async def get_connection(
    session: AsyncSession, 
    connection_id: int
) -> DatabaseConnection | None:
    ...
```

#### Async/Await

Use `async` for all database and I/O operations:

```python
# Good
async def get_user(session: AsyncSession, user_id: int) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

# Bad
def get_user(session: Session, user_id: int) -> User:
    return session.query(User).filter(User.id == user_id).first()
```

#### Docstrings

Use Google-style docstrings:

```python
async def analyze_database(connection_id: int) -> None:
    """
    Analyze a database and store insights.
    
    This function extracts metadata, generates insights,
    and stores embeddings in the vector database.
    
    Args:
        connection_id: The database connection ID to analyze.
        
    Raises:
        ConnectionNotFoundError: If connection doesn't exist.
    """
```

### Frontend (TypeScript/React)

#### File Organization

```
component/
├── ComponentName.tsx      # Main component
├── ComponentName.test.tsx # Tests
└── index.ts               # Export
```

#### Naming Conventions

- **Files**: `kebab-case.tsx` or `PascalCase.tsx` for components
- **Components**: `PascalCase`
- **Hooks**: `useCamelCase`
- **Utilities**: `camelCase`

#### Component Structure

```typescript
'use client' // If using client-side features

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

interface Props {
  id: number
  title: string
}

export function MyComponent({ id, title }: Props) {
  const [state, setState] = useState<string>('')
  
  const { data, isLoading } = useQuery({
    queryKey: ['myData', id],
    queryFn: () => fetchData(id),
  })
  
  if (isLoading) return <Loading />
  
  return <div>{/* JSX */}</div>
}
```

---

## Adding New Features

### Adding a New Backend Module

1. **Create module directory**:
   ```
   backend/app/newmodule/
   ├── __init__.py
   ├── router.py
   ├── service.py
   ├── models.py
   └── schemas.py
   ```

2. **Define models** (`models.py`):
   ```python
   from sqlmodel import Field, SQLModel
   
   class NewEntity(SQLModel, table=True):
       __tablename__ = "new_entities"
       id: int | None = Field(default=None, primary_key=True)
       name: str = Field(max_length=100)
   ```

3. **Create service** (`service.py`):
   ```python
   from sqlalchemy.ext.asyncio import AsyncSession
   from sqlmodel import select
   from .models import NewEntity
   
   async def get_entity(session: AsyncSession, entity_id: int) -> NewEntity | None:
       result = await session.execute(
           select(NewEntity).where(NewEntity.id == entity_id)
       )
       return result.scalar_one_or_none()
   ```

4. **Define schemas** (`schemas.py`):
   ```python
   from pydantic import BaseModel
   
   class NewEntityCreate(BaseModel):
       name: str
   
   class NewEntityResponse(BaseModel):
       id: int
       name: str
   ```

5. **Create router** (`router.py`):
   ```python
   from fastapi import APIRouter, Depends
   from sqlalchemy.ext.asyncio import AsyncSession
   
   from app.database import get_session
   from app.auth.dependencies import get_current_user
   from .service import get_entity
   from .schemas import NewEntityResponse
   
   router = APIRouter()
   
   @router.get("/{entity_id}", response_model=NewEntityResponse)
   async def get_entity_endpoint(
       entity_id: int,
       session: AsyncSession = Depends(get_session),
       current_user = Depends(get_current_user),
   ):
       return await get_entity(session, entity_id)
   ```

6. **Register router** (`main.py`):
   ```python
   from app.newmodule.router import router as newmodule_router
   
   app.include_router(newmodule_router, prefix="/newmodule", tags=["New Module"])
   ```

7. **Run migrations**:
   ```bash
   make migrate-create name=add_new_entities
   make migrate
   ```

### Adding a New Frontend Page

1. **Create page directory**:
   ```
   frontend/src/app/newpage/
   └── page.tsx
   ```

2. **Create the page**:
   ```typescript
   'use client'
   
   import { useQuery } from '@tanstack/react-query'
   import { api } from '@/lib/api'
   
   export default function NewPage() {
     const { data, isLoading, error } = useQuery({
       queryKey: ['newData'],
       queryFn: async () => {
         const response = await api.get('/newmodule')
         return response.data
       },
     })
     
     if (isLoading) return <div>Loading...</div>
     if (error) return <div>Error loading data</div>
     
     return (
       <div className="container mx-auto p-4">
         <h1 className="text-2xl font-bold">New Page</h1>
         {/* Content */}
       </div>
     )
   }
   ```

3. **Add API client functions** (`lib/api.ts`):
   ```typescript
   export const newModuleApi = {
     list: () => api.get('/newmodule'),
     get: (id: number) => api.get(`/newmodule/${id}`),
     create: (data: NewEntityCreate) => api.post('/newmodule', data),
   }
   ```

### Adding a New LangGraph Agent Node

1. **Define the node function** (`agent/graph.py`):
   ```python
   async def new_node(state: AgentState) -> AgentState:
       """
       New processing step.
       """
       # Access state
       question = state["question"]
       
       # Process
       result = await some_operation(question)
       
       # Update state
       state["new_field"] = result
       
       return state
   ```

2. **Update AgentState**:
   ```python
   class AgentState(TypedDict):
       # ... existing fields
       new_field: str | None
   ```

3. **Add node to graph**:
   ```python
   def create_agent_graph() -> StateGraph:
       workflow = StateGraph(AgentState)
       
       workflow.add_node("understand", understand_node)
       workflow.add_node("new_step", new_node)  # Add new node
       workflow.add_node("retrieve", retrieve_node)
       workflow.add_node("generate", generate_node)
       
       workflow.set_entry_point("understand")
       workflow.add_edge("understand", "new_step")  # Update edges
       workflow.add_edge("new_step", "retrieve")
       workflow.add_edge("retrieve", "generate")
       workflow.add_edge("generate", END)
       
       return workflow.compile()
   ```

---

## Testing

### Backend Tests

```bash
# Run all backend tests
make test-backend

# Run with coverage
cd backend && poetry run pytest tests/ -v --cov=app --cov-report=term-missing

# Run specific test file
cd backend && poetry run pytest tests/test_auth.py -v

# Run specific test
cd backend && poetry run pytest tests/test_auth.py::test_login -v
```

#### Writing Tests

```python
import pytest
from httpx import AsyncClient

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_create_connection(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/connections",
        json={
            "name": "Test DB",
            "host": "localhost",
            "port": 5432,
            "database": "test",
            "username": "test",
            "password": "test",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Test DB"
```

### Frontend Tests

```bash
# Run frontend tests
make test-frontend

# Or directly
cd frontend && npm run test
```

---

## Debugging

### Backend Debugging

#### Enable Debug Mode

```bash
# In .env
BACKEND_DEBUG=true
```

This enables:
- SQL query logging
- Detailed error messages
- Auto-reload on file changes

#### Using Debugger

```python
# Add breakpoint
import pdb; pdb.set_trace()

# Or use ipdb
import ipdb; ipdb.set_trace()
```

#### Logging

```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Detailed info")
logger.info("General info")
logger.warning("Warning message")
logger.error("Error occurred", exc_info=True)
```

### Frontend Debugging

#### React Query DevTools

Add to development:

```typescript
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  )
}
```

#### Browser DevTools

- **React DevTools**: Inspect component tree and props
- **Network Tab**: Monitor API requests
- **Console**: View errors and logs

### Database Debugging

```bash
# Connect to system database
make shell-db

# View tables
\dt

# Describe table
\d table_name

# Run query
SELECT * FROM users LIMIT 10;
```

### Qdrant Debugging

Access the dashboard at http://localhost:6333/dashboard to:
- View collections
- Browse points
- Test queries

---

## Common Issues

### "Connection refused" to services

**Cause**: Services not started or wrong ports.

**Solution**:
```bash
# Check service status
make status

# Restart services
make restart
```

### "model not found" from Ollama

**Cause**: Model not pulled.

**Solution**:
```bash
make ollama-pull
```

### Database migration errors

**Cause**: Schema mismatch.

**Solution**:
```bash
# Check current migration
cd backend && poetry run alembic current

# Generate new migration
cd backend && poetry run alembic revision --autogenerate -m "fix_schema"

# Apply migration
cd backend && poetry run alembic upgrade head
```

### Qdrant dimension mismatch

**Cause**: Embedding model changed.

**Solution**:
```bash
# Delete and recreate collection
# Access Qdrant at http://localhost:6333/dashboard
# Delete collection "database_insights"
# Re-analyze connections
```

### JWT token expired

**Cause**: Token lifetime exceeded.

**Solution**: Frontend automatically redirects to login. Adjust `JWT_EXPIRE_MINUTES` in `.env` if needed.

### CORS errors

**Cause**: Frontend URL not in allowed origins.

**Solution**: Add URL to `CORS_ORIGINS` in `.env`:
```bash
CORS_ORIGINS=["http://localhost:3000", "http://your-domain.com"]
```

---

## Code Style & Linting

### Backend

```bash
# Run linters
make lint

# Format code
make format

# Or manually:
cd backend && poetry run ruff check app/ tests/
cd backend && poetry run ruff format app/ tests/
cd backend && poetry run mypy app/
```

### Frontend

```bash
# Run linter
cd frontend && npm run lint

# Format code
cd frontend && npm run format
```

### Pre-commit Hooks

Install pre-commit hooks:

```bash
cd backend && poetry run pre-commit install
```

This runs linting and formatting on every commit.
