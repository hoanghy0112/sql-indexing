"""App module - import models here to ensure they're registered."""
from app.users.models import User
from app.connections.models import (
    DatabaseConnection,
    ConnectionShare,
    TableInsight,
    ColumnMetadata,
)
from app.agent.models import ChatSession, ChatMessage, SQLHistory
