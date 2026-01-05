.PHONY: setup dev prod stop clean logs test lint migrate help

# Colors for terminal output
CYAN := \033[0;36m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(CYAN)Database RAG & Analytics Platform$(NC)"
	@echo "=================================="
	@echo ""
	@echo "$(GREEN)Available commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""

# =============================================================================
# Setup Commands
# =============================================================================

setup: ## Install all dependencies (Python + Node.js)
	@echo "$(GREEN)Setting up project dependencies...$(NC)"
	@if [ ! -f .env ]; then cp .env.example .env && echo "$(YELLOW)Created .env from .env.example - please configure your secrets$(NC)"; fi
	@echo "$(CYAN)Installing backend dependencies...$(NC)"
	cd backend && poetry install
	@echo "$(CYAN)Installing frontend dependencies...$(NC)"
	cd frontend && npm install
	@echo "$(GREEN)Setup complete!$(NC)"

setup-backend: ## Install only backend dependencies
	@echo "$(CYAN)Installing backend dependencies...$(NC)"
	cd backend && poetry install
	@echo "$(GREEN)Backend setup complete!$(NC)"

setup-frontend: ## Install only frontend dependencies
	@echo "$(CYAN)Installing frontend dependencies...$(NC)"
	cd frontend && npm install
	@echo "$(GREEN)Frontend setup complete!$(NC)"

# =============================================================================
# Development Commands
# =============================================================================

dev: ## Start all services for development (infrastructure + local watch mode)
	@echo "$(GREEN)Starting development environment...$(NC)"
	@echo "$(CYAN)Starting infrastructure services...$(NC)"
	docker compose up -d system-db qdrant redis kafka zookeeper ollama
	@echo "$(CYAN)Waiting for services to be ready...$(NC)"
	@sleep 5
	@echo ""
	@echo "$(GREEN)Infrastructure ready!$(NC)"
	@echo "  $(CYAN)PostgreSQL:$(NC)     localhost:$${POSTGRES_PORT:-5434}"
	@echo "  $(CYAN)Qdrant:$(NC)         http://localhost:6333/dashboard"
	@echo "  $(CYAN)Redis:$(NC)          localhost:6379"
	@echo "  $(CYAN)Ollama:$(NC)         http://localhost:$${OLLAMA_PORT:-11435}"
	@echo ""
	@echo "$(GREEN)Starting backend and frontend in watch mode...$(NC)"
	@echo "  $(CYAN)Backend API:$(NC)    http://localhost:8000"
	@echo "  $(CYAN)Frontend:$(NC)       http://localhost:3000"
	@echo ""
	@trap 'kill 0' SIGINT; \
		(cd backend && poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000) & \
		(cd frontend && npm run dev) & \
		wait

dev-docker: ## Start all services via Docker (no local watch mode)
	@echo "$(GREEN)Starting all services via Docker...$(NC)"
	docker compose up -d
	@echo ""
	@echo "$(GREEN)Services are starting...$(NC)"
	@echo "  $(CYAN)Backend API:$(NC)    http://localhost:8000"
	@echo "  $(CYAN)Frontend:$(NC)       http://localhost:3000"
	@echo "  $(CYAN)Qdrant UI:$(NC)      http://localhost:6333/dashboard"
	@echo "  $(CYAN)Ollama:$(NC)         http://localhost:11434"
	@echo ""
	@echo "$(YELLOW)Run 'make logs' to view logs$(NC)"

dev-backend: ## Start only backend with dependencies (watch mode)
	@echo "$(GREEN)Starting backend services...$(NC)"
	docker compose up -d system-db qdrant redis ollama
	@echo "$(CYAN)Waiting for services to be ready...$(NC)"
	sleep 5
	cd backend && poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Start only frontend (assumes backend is running)
	@echo "$(GREEN)Starting frontend...$(NC)"
	cd frontend && npm run dev

# =============================================================================
# Production Commands
# =============================================================================

prod: ## Build and start all services for production
	@echo "$(GREEN)Building production images...$(NC)"
	docker compose -f docker compose.prod.yml build
	@echo "$(GREEN)Starting production environment...$(NC)"
	docker compose -f docker compose.prod.yml up -d
	@echo "$(GREEN)Production environment is running!$(NC)"

prod-build: ## Build production Docker images only
	@echo "$(GREEN)Building production images...$(NC)"
	docker compose -f docker compose.prod.yml build

# =============================================================================
# Service Management
# =============================================================================

stop: ## Stop all services
	@echo "$(YELLOW)Stopping all services...$(NC)"
	docker compose down
	@echo "$(GREEN)All services stopped.$(NC)"

clean: ## Stop all services and remove volumes (WARNING: deletes data!)
	@echo "$(RED)WARNING: This will delete all data!$(NC)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	docker compose down -v
	@echo "$(GREEN)Cleaned up all containers and volumes.$(NC)"

restart: ## Restart all services
	@echo "$(YELLOW)Restarting all services...$(NC)"
	docker compose restart
	@echo "$(GREEN)All services restarted.$(NC)"

logs: ## View logs from all services
	docker compose logs -f

logs-backend: ## View backend logs only
	docker compose logs -f backend

logs-frontend: ## View frontend logs only
	docker compose logs -f frontend

status: ## Show status of all services
	@echo "$(CYAN)Service Status:$(NC)"
	docker compose ps

# =============================================================================
# Database Commands
# =============================================================================

migrate: ## Run database migrations
	@echo "$(GREEN)Running database migrations...$(NC)"
	cd backend && poetry run alembic upgrade head
	@echo "$(GREEN)Migrations complete!$(NC)"

migrate-create: ## Create a new migration (usage: make migrate-create name=migration_name)
	@echo "$(GREEN)Creating new migration: $(name)$(NC)"
	cd backend && poetry run alembic revision --autogenerate -m "$(name)"

migrate-rollback: ## Rollback last migration
	@echo "$(YELLOW)Rolling back last migration...$(NC)"
	cd backend && poetry run alembic downgrade -1
	@echo "$(GREEN)Rollback complete!$(NC)"

# =============================================================================
# Testing & Quality
# =============================================================================

test: ## Run all tests
	@echo "$(GREEN)Running backend tests...$(NC)"
	cd backend && poetry run pytest tests/ -v
	@echo "$(GREEN)Running frontend tests...$(NC)"
	cd frontend && npm run test

test-backend: ## Run backend tests only
	@echo "$(GREEN)Running backend tests...$(NC)"
	cd backend && poetry run pytest tests/ -v --cov=app --cov-report=term-missing

test-frontend: ## Run frontend tests only
	@echo "$(GREEN)Running frontend tests...$(NC)"
	cd frontend && npm run test

lint: ## Run linters on all code
	@echo "$(GREEN)Linting backend...$(NC)"
	cd backend && poetry run ruff check app/ tests/
	cd backend && poetry run mypy app/
	@echo "$(GREEN)Linting frontend...$(NC)"
	cd frontend && npm run lint
	@echo "$(GREEN)Linting complete!$(NC)"

format: ## Format all code
	@echo "$(GREEN)Formatting backend...$(NC)"
	cd backend && poetry run ruff format app/ tests/
	@echo "$(GREEN)Formatting frontend...$(NC)"
	cd frontend && npm run format
	@echo "$(GREEN)Formatting complete!$(NC)"

# =============================================================================
# Model Management
# =============================================================================

ollama-pull: ## Pull required Ollama models
	@echo "$(GREEN)Pulling Ollama models...$(NC)"
	docker compose exec ollama ollama pull qwen3:4b
	@echo "$(GREEN)Models pulled successfully!$(NC)"

ollama-list: ## List available Ollama models
	docker compose exec ollama ollama list

# =============================================================================
# Utility Commands
# =============================================================================

shell-backend: ## Open a shell in the backend container
	docker compose exec backend /bin/bash

shell-db: ## Open psql shell in the system database
	docker compose exec system-db psql -U sqlindex -d sqlindex_system

shell-redis: ## Open redis-cli shell
	docker compose exec redis redis-cli

health: ## Check health of all services
	@echo "$(CYAN)Checking service health...$(NC)"
	@echo ""
	@echo "System DB:"
	@docker compose exec system-db pg_isready -U sqlindex && echo "  $(GREEN)✓ Healthy$(NC)" || echo "  $(RED)✗ Unhealthy$(NC)"
	@echo ""
	@echo "Qdrant:"
	@curl -sf http://localhost:6333/readyz && echo "  $(GREEN)✓ Healthy$(NC)" || echo "  $(RED)✗ Unhealthy$(NC)"
	@echo ""
	@echo "Redis:"
	@docker compose exec redis redis-cli ping | grep -q PONG && echo "  $(GREEN)✓ Healthy$(NC)" || echo "  $(RED)✗ Unhealthy$(NC)"
	@echo ""
	@echo "Ollama:"
	@curl -sf http://localhost:11434/api/tags > /dev/null && echo "  $(GREEN)✓ Healthy$(NC)" || echo "  $(RED)✗ Unhealthy$(NC)"
