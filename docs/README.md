# Documentation Index

Welcome to the **Database RAG & Analytics Platform** documentation. This comprehensive documentation covers all aspects of the system, from architecture to deployment.

---

## 📚 Documentation Structure

| Document | Description |
|----------|-------------|
| [01-architecture-overview.md](./01-architecture-overview.md) | High-level system architecture, component overview, and design decisions |
| [02-backend-modules.md](./02-backend-modules.md) | Detailed documentation of all backend modules and their interactions |
| [03-frontend-documentation.md](./03-frontend-documentation.md) | Frontend pages, components, state management, and API client |
| [04-data-models.md](./04-data-models.md) | Entity relationship diagram, database tables, enums, and schemas |
| [05-api-reference.md](./05-api-reference.md) | Complete REST API reference with request/response examples |
| [06-development-guide.md](./06-development-guide.md) | Development setup, conventions, adding features, testing, debugging |
| [07-configuration-reference.md](./07-configuration-reference.md) | All environment variables and configuration options |
| [08-deployment-guide.md](./08-deployment-guide.md) | Production deployment with Docker, Kubernetes, SSL, and scaling |

---

## 🚀 Quick Links

### Getting Started
- [Prerequisites](./06-development-guide.md#prerequisites)
- [Initial Setup](./06-development-guide.md#initial-setup)
- [Starting Services](./06-development-guide.md#starting-services)

### Architecture
- [System Overview](./01-architecture-overview.md#system-overview)
- [Data Flow](./01-architecture-overview.md#data-flow)
- [Technology Stack](./01-architecture-overview.md#technology-stack-summary)

### Development
- [Backend Conventions](./06-development-guide.md#backend-python)
- [Frontend Conventions](./06-development-guide.md#frontend-typescriptreact)
- [Adding New Features](./06-development-guide.md#adding-new-features)

### API
- [Authentication](./05-api-reference.md#authentication)
- [Connections API](./05-api-reference.md#database-connection-endpoints)
- [Chat API](./05-api-reference.md#chat-endpoints)

### Deployment
- [Docker Compose](./08-deployment-guide.md#docker-compose-production)
- [Kubernetes](./08-deployment-guide.md#kubernetes-deployment)
- [SSL Configuration](./08-deployment-guide.md#ssltls-configuration)

---

## 🏗️ System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                    │
│                        (Next.js + React Query)                          │
│                                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │    Login    │  │    Home     │  │  Database   │  │   Public    │    │
│  │   Register  │  │ (Dashboard) │  │   Detail    │  │    Chat     │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                               BACKEND                                    │
│                               (FastAPI)                                  │
│                                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │    Auth     │  │ Connections │  │Intelligence │  │    Agent    │    │
│  │   Module    │  │   Module    │  │   Module    │  │    Module   │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────────────┐    │
│  │    Users    │  │   System    │  │         RAG Tools            │    │
│  │   Module    │  │   Module    │  │  (Vector Search, SQL Exec)   │    │
│  └─────────────┘  └─────────────┘  └──────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           INFRASTRUCTURE                                 │
│                                                                          │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ │
│  │PostgreSQL │ │  Qdrant   │ │   Redis   │ │  Ollama   │ │   Kafka   │ │
│  │  (System) │ │ (Vectors) │ │ (Cache)   │ │   (LLM)   │ │  (Queue)  │ │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
sql-indexing/
├── backend/                    # FastAPI Backend
│   └── app/
│       ├── main.py            # Application entry
│       ├── config.py          # Configuration
│       ├── database.py        # SQLAlchemy setup
│       ├── agent/             # LangGraph chat agent
│       ├── auth/              # Authentication
│       ├── connections/       # DB connections
│       ├── intelligence/      # Schema analysis
│       ├── rag/               # RAG tools
│       ├── system/            # System APIs
│       └── users/             # User management
│
├── frontend/                   # Next.js Frontend
│   └── src/
│       ├── app/               # Pages (App Router)
│       ├── components/        # React components
│       ├── lib/               # API, auth, utils
│       └── hooks/             # Custom hooks
│
├── docs/                       # Documentation
├── docker-compose.yml          # Development
├── docker-compose.prod.yml     # Production
├── Makefile                   # Commands
└── .env.example               # Configuration template
```

---

## 🔑 Key Concepts

### Database Analysis Workflow
1. User adds PostgreSQL connection
2. System extracts schema metadata
3. LLM determines indexing strategies
4. Embeddings generated and stored in Qdrant
5. Connection ready for natural language queries

### Chat Agent Workflow
1. User asks question in natural language
2. **Understand Node**: Parse intent
3. **Retrieve Node**: Vector search for relevant tables
4. **Generate Node**: Create SQL, execute, explain results

### Sharing Model
- **Owner**: Full access
- **View**: Read + chat + intelligence
- **Chat**: Read + chat only

---

## 🛠️ Common Tasks

### Add a new database connection
```bash
# Via API
curl -X POST http://localhost:8000/connections \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Database",
    "host": "localhost",
    "port": 5432,
    "database": "mydb",
    "username": "user",
    "password": "pass"
  }'
```

### Trigger re-analysis
```bash
curl -X POST http://localhost:8000/connections/1/reanalyze \
  -H "Authorization: Bearer $TOKEN"
```

### Chat with database
```bash
curl -X POST http://localhost:8000/chat/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "How many users signed up last week?"}'
```

---

## 📞 Support

For issues and questions:
1. Check [Common Issues](./06-development-guide.md#common-issues)
2. Review [Debugging Guide](./06-development-guide.md#debugging)
3. Check API documentation at http://localhost:8000/docs

---

## 📄 License

MIT License - see LICENSE file for details.
