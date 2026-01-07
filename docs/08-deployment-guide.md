# Deployment Guide

This document provides instructions for deploying the Database RAG & Analytics Platform to various environments.

---

## Table of Contents

1. [Deployment Options](#deployment-options)
2. [Docker Compose Production](#docker-compose-production)
3. [Kubernetes Deployment](#kubernetes-deployment)
4. [Environment-Specific Configuration](#environment-specific-configuration)
5. [SSL/TLS Configuration](#ssltls-configuration)
6. [Backup & Recovery](#backup--recovery)
7. [Monitoring](#monitoring)
8. [Scaling Considerations](#scaling-considerations)

---

## Deployment Options

| Option | Complexity | Best For |
|--------|------------|----------|
| Docker Compose | Low | Small teams, single server |
| Kubernetes | High | Large scale, high availability |
| Cloud Managed | Medium | AWS, GCP, Azure deployments |

---

## Docker Compose Production

### Prerequisites

- Docker Engine 24+
- Docker Compose v2+
- SSL certificates (for HTTPS)
- DNS configured

### Production Docker Compose

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  # =================================================================
  # System Database
  # =================================================================
  system-db:
    image: postgres:15-alpine
    container_name: sqlindex-system-db
    restart: always
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - system_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - sqlindex-network

  # =================================================================
  # Qdrant Vector Database
  # =================================================================
  qdrant:
    image: qdrant/qdrant:latest
    container_name: sqlindex-qdrant
    restart: always
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      QDRANT__SERVICE__GRPC_PORT: 6334
    networks:
      - sqlindex-network

  # =================================================================
  # Redis
  # =================================================================
  redis:
    image: redis:7-alpine
    container_name: sqlindex-redis
    restart: always
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD:-}
    networks:
      - sqlindex-network

  # =================================================================
  # Ollama LLM
  # =================================================================
  ollama:
    image: ollama/ollama:latest
    container_name: sqlindex-ollama
    restart: always
    volumes:
      - ollama_data:/root/.ollama
    # GPU support (uncomment if needed)
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]
    networks:
      - sqlindex-network

  # =================================================================
  # Backend API
  # =================================================================
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.prod
    container_name: sqlindex-backend
    restart: always
    depends_on:
      system-db:
        condition: service_healthy
      qdrant:
        condition: service_started
      redis:
        condition: service_started
    environment:
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@system-db:5432/${POSTGRES_DB}
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - REDIS_URL=redis://redis:6379
      - OLLAMA_BASE_URL=http://ollama:11434
      - JWT_SECRET=${JWT_SECRET}
      - JWT_ALGORITHM=HS256
      - JWT_EXPIRE_MINUTES=${JWT_EXPIRE_MINUTES:-1440}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL}
      - BACKEND_DEBUG=false
    networks:
      - sqlindex-network

  # =================================================================
  # Frontend
  # =================================================================
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.prod
      args:
        NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL}
    container_name: sqlindex-frontend
    restart: always
    depends_on:
      - backend
    networks:
      - sqlindex-network

  # =================================================================
  # Nginx Reverse Proxy
  # =================================================================
  nginx:
    image: nginx:alpine
    container_name: sqlindex-nginx
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    depends_on:
      - frontend
      - backend
    networks:
      - sqlindex-network

volumes:
  system_db_data:
  qdrant_data:
  redis_data:
  ollama_data:

networks:
  sqlindex-network:
    driver: bridge
```

### Production Dockerfiles

**Backend** (`backend/Dockerfile.prod`):

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install poetry

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --only=main --no-interaction --no-ansi

# Copy application
COPY app ./app

# Run with gunicorn
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000"]
```

**Frontend** (`frontend/Dockerfile.prod`):

```dockerfile
FROM node:18-alpine AS builder

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN npm install -g pnpm && pnpm install --frozen-lockfile

COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN pnpm build

FROM node:18-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
```

### Nginx Configuration

**`nginx/nginx.conf`**:

```nginx
events {
    worker_connections 1024;
}

http {
    upstream frontend {
        server frontend:3000;
    }

    upstream backend {
        server backend:8000;
    }

    # HTTP redirect to HTTPS
    server {
        listen 80;
        server_name your-domain.com;
        return 301 https://$server_name$request_uri;
    }

    # HTTPS server
    server {
        listen 443 ssl http2;
        server_name your-domain.com;

        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;

        # Frontend
        location / {
            proxy_pass http://frontend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_cache_bypass $http_upgrade;
        }

        # Backend API
        location /api/ {
            rewrite ^/api/(.*) /$1 break;
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Backend docs
        location /docs {
            proxy_pass http://backend/docs;
            proxy_set_header Host $host;
        }

        location /redoc {
            proxy_pass http://backend/redoc;
            proxy_set_header Host $host;
        }
    }
}
```

### Deployment Commands

```bash
# Build production images
docker compose -f docker-compose.prod.yml build

# Start production environment
docker compose -f docker-compose.prod.yml up -d

# View logs
docker compose -f docker-compose.prod.yml logs -f

# Pull LLM model
docker compose -f docker-compose.prod.yml exec ollama ollama pull qwen2.5:3b
```

---

## Kubernetes Deployment

### Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: sqlindex
```

### ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sqlindex-config
  namespace: sqlindex
data:
  QDRANT_HOST: "qdrant"
  QDRANT_PORT: "6333"
  REDIS_URL: "redis://redis:6379"
  OLLAMA_BASE_URL: "http://ollama:11434"
  EMBEDDING_MODEL: "sentence-transformers/all-MiniLM-L6-v2"
  BACKEND_DEBUG: "false"
```

### Secrets

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: sqlindex-secrets
  namespace: sqlindex
type: Opaque
stringData:
  POSTGRES_PASSWORD: "your-secure-password"
  JWT_SECRET: "your-jwt-secret"
  DATABASE_URL: "postgresql+asyncpg://sqlindex:your-secure-password@postgres:5432/sqlindex_system"
```

### Backend Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: sqlindex
spec:
  replicas: 2
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
        - name: backend
          image: your-registry/sqlindex-backend:latest
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: sqlindex-config
            - secretRef:
                name: sqlindex-secrets
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
```

### Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: sqlindex
spec:
  selector:
    app: backend
  ports:
    - port: 8000
      targetPort: 8000
```

### Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: sqlindex-ingress
  namespace: sqlindex
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts:
        - app.your-domain.com
      secretName: sqlindex-tls
  rules:
    - host: app.your-domain.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend
                port:
                  number: 3000
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: backend
                port:
                  number: 8000
```

---

## Environment-Specific Configuration

### Development

```bash
BACKEND_DEBUG=true
JWT_EXPIRE_MINUTES=10080  # 1 week for convenience
CORS_ORIGINS=["http://localhost:3000"]
```

### Staging

```bash
BACKEND_DEBUG=false
JWT_EXPIRE_MINUTES=1440  # 24 hours
CORS_ORIGINS=["https://staging.your-domain.com"]
```

### Production

```bash
BACKEND_DEBUG=false
JWT_EXPIRE_MINUTES=60  # 1 hour
CORS_ORIGINS=["https://app.your-domain.com"]
```

---

## SSL/TLS Configuration

### Using Let's Encrypt (Certbot)

```bash
# Install certbot
sudo apt install certbot

# Get certificate
sudo certbot certonly --standalone -d your-domain.com

# Certificates will be at:
# /etc/letsencrypt/live/your-domain.com/fullchain.pem
# /etc/letsencrypt/live/your-domain.com/privkey.pem
```

### Auto-renewal

```bash
# Add cron job
0 0 1 * * certbot renew --quiet && docker compose -f docker-compose.prod.yml restart nginx
```

---

## Backup & Recovery

### Database Backup

```bash
# Backup
docker compose exec system-db pg_dump -U sqlindex sqlindex_system > backup_$(date +%Y%m%d).sql

# Restore
docker compose exec -T system-db psql -U sqlindex sqlindex_system < backup_20240115.sql
```

### Qdrant Backup

```bash
# Qdrant data is in the volume
docker compose exec qdrant tar czf /tmp/qdrant_backup.tar.gz /qdrant/storage
docker cp sqlindex-qdrant:/tmp/qdrant_backup.tar.gz ./qdrant_backup.tar.gz
```

### Full Backup Script

```bash
#!/bin/bash
BACKUP_DIR="/backups/sqlindex/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# Database
docker compose exec -T system-db pg_dump -U sqlindex sqlindex_system > $BACKUP_DIR/database.sql

# Volumes
docker run --rm -v sqlindex_system_db_data:/data -v $BACKUP_DIR:/backup alpine tar czf /backup/postgres.tar.gz /data
docker run --rm -v sqlindex_qdrant_data:/data -v $BACKUP_DIR:/backup alpine tar czf /backup/qdrant.tar.gz /data

echo "Backup completed: $BACKUP_DIR"
```

---

## Monitoring

### Health Checks

```bash
# Backend health
curl https://your-domain.com/api/health

# System stats
curl -H "Authorization: Bearer $TOKEN" https://your-domain.com/api/system/stats
```

### Logging

Configure structured JSON logging:

```python
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
        })

logging.basicConfig(
    handlers=[logging.StreamHandler()],
    level=logging.INFO,
)
logging.root.handlers[0].setFormatter(JSONFormatter())
```

### Prometheus Metrics (Future)

Expose metrics endpoint:

```python
from prometheus_client import Counter, Histogram, generate_latest

REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('http_request_latency_seconds', 'HTTP request latency')

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

---

## Scaling Considerations

### Horizontal Scaling

| Component | Strategy |
|-----------|----------|
| Backend | Multiple replicas behind load balancer |
| Frontend | Multiple replicas, static files to CDN |
| PostgreSQL | Read replicas for queries |
| Qdrant | Cluster mode for high availability |
| Redis | Redis Cluster for caching |
| Ollama | Multiple instances with load balancing |

### Vertical Scaling

| Component | Recommendation |
|-----------|----------------|
| Backend | 2-4 vCPU, 4-8 GB RAM per instance |
| Ollama | GPU (NVIDIA) for faster inference |
| PostgreSQL | SSD storage, 4-8 GB RAM |
| Qdrant | SSD storage, 2-4 GB RAM |

### Caching Strategy

1. **API responses**: Redis caching for frequent queries
2. **Embeddings**: Cache generated embeddings
3. **Static files**: CDN for frontend assets

### Database Optimization

```sql
-- Add indexes for common queries
CREATE INDEX idx_insights_connection ON table_insights(connection_id);
CREATE INDEX idx_messages_session ON chat_messages(session_id);
CREATE INDEX idx_connections_owner ON database_connections(owner_id);
```
