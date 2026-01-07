"""App module - import models here to ensure they're registered."""
from app.agent.models import ChatMessage, ChatSession, SQLHistory
from app.connections.models import (
    ColumnMetadata,
    ConnectionShare,
    DatabaseConnection,
    TableInsight,
)
from app.users.models import User
