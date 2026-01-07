# API Reference

This document provides a complete reference for all REST API endpoints.

---

## Base URL

```
http://localhost:8000
```

## Authentication

All endpoints except `/auth/register`, `/auth/login`, and `/chat/public/{token}` require authentication.

### Bearer Token

Include the JWT token in the `Authorization` header:

```
Authorization: Bearer <token>
```

---

## Health Endpoints

### GET /

Health check root endpoint.

**Response**:
```json
{
  "status": "healthy",
  "app": "Database RAG & Analytics Platform",
  "version": "0.1.0"
}
```

### GET /health

Detailed health check.

**Response**:
```json
{
  "status": "healthy",
  "database": "connected",
  "vector_store": "connected"
}
```

---

## Authentication Endpoints

### POST /auth/register

Register a new user.

**Request Body**:
```json
{
  "username": "johndoe",
  "email": "john@example.com",
  "password": "securepassword123"
}
```

**Response** (201):
```json
{
  "id": 1,
  "username": "johndoe",
  "email": "john@example.com",
  "is_active": true
}
```

**Errors**:
- `400` - Username/email already exists
- `422` - Validation error

---

### POST /auth/login

Authenticate and get JWT token.

**Request Body**:
```json
{
  "username": "johndoe",
  "password": "securepassword123"
}
```

**Response** (200):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

**Errors**:
- `401` - Invalid credentials

---

### GET /auth/me

Get current authenticated user.

**Response**:
```json
{
  "id": 1,
  "username": "johndoe",
  "email": "john@example.com",
  "is_active": true
}
```

---

### POST /auth/refresh

Refresh JWT token.

**Response**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

---

## Database Connection Endpoints

### GET /connections

List all connections accessible by the user.

**Response**:
```json
[
  {
    "id": 1,
    "name": "Production DB",
    "description": "Main production database",
    "database": "myapp_prod",
    "host": "db.example.com",
    "port": 5432,
    "status": "ready",
    "status_message": "Analysis complete",
    "analysis_progress": 100.0,
    "last_analyzed_at": "2024-01-15T10:30:00Z",
    "is_owner": true,
    "permission": null
  }
]
```

---

### POST /connections

Create a new database connection.

**Request Body**:
```json
{
  "name": "My Database",
  "description": "Optional description",
  "host": "localhost",
  "port": 5432,
  "database": "mydb",
  "username": "postgres",
  "password": "mypassword",
  "ssl_mode": "prefer"
}
```

**Response** (201):
```json
{
  "id": 1,
  "name": "My Database",
  "status": "pending",
  "message": "Connection created. Analysis will start shortly."
}
```

---

### POST /connections/from-url

Create connection from a PostgreSQL URL.

**Request Body**:
```json
{
  "name": "My Database",
  "description": "Optional description",
  "connection_url": "postgresql://user:pass@host:5432/dbname"
}
```

---

### GET /connections/{id}

Get connection details.

**Response**:
```json
{
  "id": 1,
  "name": "My Database",
  "description": "Description",
  "database": "mydb",
  "host": "localhost",
  "port": 5432,
  "ssl_mode": "prefer",
  "status": "ready",
  "status_message": "Analysis complete",
  "analysis_progress": 100.0,
  "last_analyzed_at": "2024-01-15T10:30:00Z",
  "created_at": "2024-01-14T08:00:00Z",
  "is_owner": true,
  "permission": null
}
```

---

### PUT /connections/{id}

Update connection settings.

**Request Body** (partial update):
```json
{
  "name": "Updated Name",
  "description": "Updated description",
  "password": "newpassword"
}
```

**Response**: Updated connection object.

---

### DELETE /connections/{id}

Delete a connection and all related data.

**Response** (200):
```json
{
  "message": "Connection deleted successfully"
}
```

---

### POST /connections/{id}/test

Test database connection.

**Response**:
```json
{
  "success": true,
  "message": "Connection successful",
  "server_version": "PostgreSQL 15.1"
}
```

Or on failure:
```json
{
  "success": false,
  "message": "Connection failed: password authentication failed",
  "server_version": null
}
```

---

### POST /connections/{id}/reanalyze

Trigger re-analysis of database.

**Response**:
```json
{
  "message": "Re-analysis started",
  "connection_id": 1
}
```

---

### GET /connections/{id}/shares

List all shares for a connection.

**Response**:
```json
[
  {
    "id": 1,
    "user_id": 2,
    "username": "jane",
    "email": "jane@example.com",
    "permission": "view",
    "created_at": "2024-01-15T10:00:00Z"
  }
]
```

---

### POST /connections/{id}/shares

Share connection with a user.

**Request Body**:
```json
{
  "user_id": 2,
  "permission": "view"
}
```

**Permissions**: `chat`, `view`, `owner`

---

### DELETE /connections/{id}/shares/{user_id}

Remove a share.

**Response** (200):
```json
{
  "message": "Share removed"
}
```

---

## Intelligence Endpoints

### GET /intelligence/{connection_id}/insights

Get all table insights for a connection.

**Response**:
```json
[
  {
    "id": 1,
    "schema_name": "public",
    "table_name": "users",
    "row_count": 1234,
    "summary": "Table public.users | 1,234 rows | 5 columns",
    "insight_document": "Table: public.users\n...",
    "vector_id": "a1b2c3d4e5f6",
    "columns": [
      {
        "name": "id",
        "data_type": "integer",
        "is_primary_key": true,
        "is_foreign_key": false,
        "distinct_count": 1234,
        "indexing_strategy": "skip",
        "categorical_values": null
      },
      {
        "name": "status",
        "data_type": "character varying",
        "is_primary_key": false,
        "is_foreign_key": false,
        "distinct_count": 3,
        "indexing_strategy": "categorical",
        "categorical_values": ["active", "inactive", "pending"]
      }
    ]
  }
]
```

---

### GET /intelligence/{connection_id}/stats

Get analysis statistics.

**Response**:
```json
{
  "connection_id": 1,
  "table_count": 15,
  "total_columns": 87,
  "total_rows": 50000,
  "categorical_columns": 12,
  "vector_indexed_columns": 8,
  "skipped_columns": 67,
  "vector_store_documents": 15
}
```

---

### PUT /intelligence/{connection_id}/insights/{insight_id}

Update an insight (summary or document).

**Request Body**:
```json
{
  "summary": "Updated summary",
  "insight_document": "Updated document text"
}
```

---

## Chat Endpoints

### POST /chat/{connection_id}

Send a chat message to query the database.

**Request Body**:
```json
{
  "question": "How many users signed up last month?",
  "explain_mode": true,
  "session_id": null
}
```

**Response**:
```json
{
  "session_id": 1,
  "message_id": 1,
  "response": "{\"sql\": \"SELECT COUNT(*) FROM users WHERE created_at >= '2024-01-01'\", \"explanation\": \"This query counts users created in January 2024.\", \"data\": [[150]], \"columns\": [\"count\"]}",
  "sql": "SELECT COUNT(*) FROM users WHERE created_at >= '2024-01-01'",
  "explanation": "This query counts users created in January 2024.",
  "data": [[150]],
  "columns": ["count"],
  "error": null
}
```

With `explain_mode: false`:
```json
{
  "session_id": 1,
  "message_id": 1,
  "response": "count\n150",
  "sql": "SELECT COUNT(*) FROM users WHERE created_at >= '2024-01-01'",
  "explanation": null,
  "data": [[150]],
  "columns": ["count"],
  "error": null
}
```

---

### GET /chat/{connection_id}/sessions

List chat sessions.

**Response**:
```json
{
  "sessions": [
    {
      "id": 1,
      "title": "User statistics queries",
      "is_public": false,
      "message_count": 5,
      "created_at": "2024-01-15T10:00:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

### GET /chat/{connection_id}/sessions/{session_id}

Get chat session history.

**Response**:
```json
{
  "session_id": 1,
  "title": "User statistics queries",
  "messages": [
    {
      "id": 1,
      "role": "user",
      "content": "How many users do we have?",
      "sql_query": null,
      "created_at": "2024-01-15T10:00:00Z"
    },
    {
      "id": 2,
      "role": "assistant",
      "content": "The database contains 1,234 users.",
      "sql_query": "SELECT COUNT(*) FROM users",
      "execution_time_ms": 45,
      "row_count": 1,
      "created_at": "2024-01-15T10:00:02Z"
    }
  ],
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

---

### DELETE /chat/{connection_id}/sessions/{session_id}

Delete a chat session.

**Response**:
```json
{
  "message": "Session deleted"
}
```

---

### POST /chat/{connection_id}/sessions/{session_id}/share

Toggle public sharing for a session.

**Response**:
```json
{
  "is_public": true,
  "share_token": "abc123def456",
  "share_url": "http://localhost:3000/chat/abc123def456"
}
```

---

### GET /chat/public/{share_token}

Get publicly shared chat (no authentication required).

**Response**:
```json
{
  "session_id": 1,
  "title": "User statistics queries",
  "database_name": "mydb",
  "connection_name": "Production DB",
  "messages": [...],
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**Errors**:
- `404` - Share token not found or not public

---

## User Endpoints

### GET /users/search

Search for users by username or email.

**Query Parameters**:
- `q` (required) - Search query

**Response**:
```json
[
  {
    "id": 2,
    "username": "jane",
    "email": "jane@example.com"
  }
]
```

---

### PUT /users/me

Update current user profile.

**Request Body**:
```json
{
  "email": "newemail@example.com"
}
```

---

### POST /users/me/change-password

Change password.

**Request Body**:
```json
{
  "current_password": "oldpassword",
  "new_password": "newpassword123"
}
```

**Errors**:
- `400` - Current password incorrect

---

## System Endpoints

### GET /system/health

Detailed system health check.

**Response**:
```json
{
  "status": "healthy",
  "database": "connected",
  "vector_store": "connected",
  "llm": "available",
  "redis": "connected"
}
```

---

### GET /system/connections/{connection_id}/status

Get connection analysis status.

**Response**:
```json
{
  "connection_id": 1,
  "status": "analyzing",
  "status_message": "Processing table 'users' (3/15)...",
  "progress": 35.5
}
```

---

### GET /system/connections/{connection_id}/sql-history

Get SQL query history.

**Query Parameters**:
- `limit` (default: 50) - Max results
- `offset` (default: 0) - Offset for pagination

**Response**:
```json
[
  {
    "id": 1,
    "session_id": 1,
    "sql_query": "SELECT COUNT(*) FROM users",
    "execution_time_ms": 45,
    "row_count": 1,
    "created_at": "2024-01-15T10:00:00Z"
  }
]
```

---

### GET /system/stats

Get system statistics.

**Response**:
```json
{
  "total_users": 10,
  "total_connections": 25,
  "total_chat_sessions": 150,
  "total_messages": 500,
  "vector_store": {
    "vectors_count": 125,
    "indexed_vectors_count": 125,
    "points_count": 125,
    "status": "green"
  }
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message"
}
```

### Validation Errors (422)

```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

### Common HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 422 | Validation Error |
| 500 | Internal Server Error |
