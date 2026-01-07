"""
Vectorizer

Handles embedding generation and vector storage in Qdrant.
"""

import hashlib
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer

from app.config import get_settings

settings = get_settings()

# Lazy-loaded clients
_qdrant_client: QdrantClient | None = None
_embedding_model: SentenceTransformer | None = None


def get_qdrant_client() -> QdrantClient:
    """Get or create Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
    return _qdrant_client


def get_embedding_model() -> SentenceTransformer:
    """Get or create embedding model."""
    global _embedding_model
    if _embedding_model is None:
        model_path = settings.embedding_model_path or settings.embedding_model
        _embedding_model = SentenceTransformer(model_path)
    return _embedding_model


async def ensure_collection_exists() -> None:
    """Ensure the Qdrant collection exists."""
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection_name

    collections = client.get_collections()
    collection_names = [c.name for c in collections.collections]

    if collection_name not in collection_names:
        # Create new collection
        model = get_embedding_model()
        embedding_dim = model.get_sentence_embedding_dimension()

        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=embedding_dim,
                distance=models.Distance.COSINE,
            ),
        )
    else:
        # Check if dimensions match
        model = get_embedding_model()
        embedding_dim = model.get_sentence_embedding_dimension()
        
        collection_info = client.get_collection(collection_name)
        current_dim = collection_info.config.params.vectors.size
        
        if current_dim != embedding_dim:
            # Dimension mismatch - recreate collection
            print(f"Dimension mismatch (current: {current_dim}, new: {embedding_dim}). Recreating collection...")
            client.delete_collection(collection_name)
            
            client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=embedding_dim,
                    distance=models.Distance.COSINE,
                ),
            )


def generate_vector_id(connection_id: int, table_name: str) -> str:
    """Generate a deterministic vector ID."""
    content = f"{connection_id}:{table_name}"
    return hashlib.md5(content.encode()).hexdigest()


async def embed_text(text: str) -> list[float]:
    """Generate embedding for a text."""
    model = get_embedding_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


async def upsert_document(
    connection_id: int,
    table_name: str,
    schema_name: str,
    document: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    Upsert a document embedding to Qdrant.

    Returns the vector ID.
    """
    await ensure_collection_exists()

    client = get_qdrant_client()
    collection_name = settings.qdrant_collection_name

    # Generate embedding
    embedding = await embed_text(document)

    # Generate deterministic ID
    vector_id = generate_vector_id(connection_id, f"{schema_name}.{table_name}")

    # Prepare payload
    payload = {
        "connection_id": connection_id,
        "table_name": table_name,
        "schema_name": schema_name,
        "document": document[:10000],  # Limit document size in payload
        **(metadata or {}),
    }

    # Upsert to Qdrant
    client.upsert(
        collection_name=collection_name,
        points=[
            models.PointStruct(
                id=vector_id,
                vector=embedding,
                payload=payload,
            )
        ],
    )

    return vector_id


async def search_similar(
    query: str,
    connection_id: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """
    Search for similar documents in the vector store.

    Args:
        query: Search query text
        connection_id: Optional filter by connection
        limit: Maximum results to return

    Returns:
        List of matching documents with scores
    """
    await ensure_collection_exists()

    client = get_qdrant_client()
    collection_name = settings.qdrant_collection_name

    # Generate query embedding
    query_embedding = await embed_text(query)

    # Build filter
    filter_conditions = []
    if connection_id is not None:
        filter_conditions.append(
            models.FieldCondition(
                key="connection_id",
                match=models.MatchValue(value=connection_id),
            )
        )

    query_filter = None
    if filter_conditions:
        query_filter = models.Filter(must=filter_conditions)

    # Search
    results = client.query_points(
        collection_name=collection_name,
        query=query_embedding,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    ).points

    return [
        {
            "id": result.id,
            "score": result.score,
            "table_name": result.payload.get("table_name"),
            "schema_name": result.payload.get("schema_name"),
            "document": result.payload.get("document"),
            "connection_id": result.payload.get("connection_id"),
        }
        for result in results
    ]


async def delete_connection_documents(connection_id: int) -> None:
    """Delete all documents for a connection."""
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection_name

    try:
        client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="connection_id",
                            match=models.MatchValue(value=connection_id),
                        )
                    ]
                )
            ),
        )
    except Exception:
        # Collection might not exist yet
        pass


async def get_collection_stats() -> dict:
    """Get statistics about the vector collection."""
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection_name

    try:
        info = client.get_collection(collection_name)
        return {
            "vectors_count": info.vectors_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "points_count": info.points_count,
            "status": info.status.value,
        }
    except Exception:
        return {
            "vectors_count": 0,
            "indexed_vectors_count": 0,
            "points_count": 0,
            "status": "not_created",
        }
