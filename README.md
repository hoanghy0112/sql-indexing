# Database RAG & Analytics Platform

A production-ready platform that allows users to connect PostgreSQL databases, automatically analyze their schema/metadata using AI, and chat with their data using a multi-agent system.

## 🚀 Features

- **Database Connection Management**: Connect and manage multiple PostgreSQL databases
- **Intelligent Schema Analysis**: Automatic metadata extraction, insight generation, and vectorization
- **AI-Powered Chat**: Ask questions about your data in natural language
- **Smart Indexing**: LLM-driven decisions on optimal indexing strategies
- **Multi-User Support**: Share databases with team members
- **Real-time Progress**: Live updates during database analysis

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11+, FastAPI, SQLModel |
| AI | LangChain, LangGraph, Ollama (qwen3:4b) |
| Embeddings | google/gemma-embedding-300m |
| Database | PostgreSQL 15 |
| Vector Store | Qdrant |
| Message Queue | Kafka + Zookeeper |
| Cache | Redis |
| Frontend | Next.js 14, React Query, Tailwind CSS, Shadcn UI |

## 📋 Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+
- Poetry (Python package manager)
- NVIDIA GPU (optional, for faster LLM inference)

## 🏃 Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd sql-indexing

# Copy environment file and configure
cp .env.example .env
# Edit .env with your configurations

# Install dependencies
make setup
```

### 2. Start Development Environment

```bash
# Start all services
make dev

# Pull required Ollama model (first time only)
make ollama-pull
```

### 3. Access the Application

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Qdrant Dashboard**: http://localhost:6333/dashboard

## 📁 Project Structure

```
sql-indexing/
├── docker-compose.yml      # Development Docker orchestration
├── docker-compose.prod.yml # Production Docker orchestration
├── Makefile               # Build and run commands
├── .env.example           # Environment template
│
├── backend/               # FastAPI Backend
│   ├── app/
│   │   ├── main.py       # Application entry point
│   │   ├── config.py     # Configuration management
│   │   ├── auth/         # Authentication module
│   │   ├── users/        # User management
│   │   ├── connections/  # DB connection management
│   │   ├── intelligence/ # Schema analysis engine
│   │   ├── rag/          # RAG tools and retrieval
│   │   ├── agent/        # LangGraph chat agent
│   │   └── system/       # System management APIs
│   └── tests/
│
├── frontend/              # Next.js Frontend
│   └── src/
│       ├── app/          # App Router pages
│       ├── components/   # React components
│       ├── lib/          # Utilities and API client
│       └── hooks/        # React Query hooks
│
└── docs/                  # Documentation
```

## 🔧 Available Commands

```bash
make help          # Show all available commands
make setup         # Install all dependencies
make dev           # Start development environment
make stop          # Stop all services
make logs          # View service logs
make test          # Run all tests
make lint          # Run linters
make migrate       # Run database migrations
make ollama-pull   # Pull required LLM models
make health        # Check service health
```

## 🔐 Environment Variables

Key environment variables (see `.env.example` for full list):

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | System database password | - |
| `JWT_SECRET` | JWT signing secret | - |
| `OLLAMA_MODEL` | LLM model name | qwen3:4b |
| `EMBEDDING_MODEL` | Embedding model | google/gemma-embedding-300m |
| `CATEGORY_THRESHOLD` | Max distinct values for categorical | 100 |

## 📖 API Documentation

Once the backend is running, access the interactive API docs:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🧪 Testing

```bash
# Run all tests
make test

# Run backend tests with coverage
make test-backend

# Run frontend tests
make test-frontend
```

## 🚢 Production Deployment

```bash
# Build production images
make prod-build

# Start production environment
make prod
```

## 📝 License

MIT License - see [LICENSE](LICENSE) for details.
