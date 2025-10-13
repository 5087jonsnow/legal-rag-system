from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    Range,
)
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime

from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class VectorStore:
    """Qdrant vector database client"""

    def __init__(self):
        self.client = None
        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self._initialized = False

    def _ensure_initialized(self):
        """Ensure client is initialized (synchronous fallback)"""
        if self._initialized and self.client is not None:
            return
        
        try:
            logger.info("Initializing Qdrant client...")
            self.client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                api_key=settings.QDRANT_API_KEY,
            )

            # Create collection if it doesn't exist
            collections = self.client.get_collections().collections
            collection_exists = any(c.name == self.collection_name for c in collections)
            if not collection_exists:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=settings.EMBEDDING_DIMENSION,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created collection: {self.collection_name}")
            else:
                logger.info(f"Collection already exists: {self.collection_name}")

            self._initialized = True
            logger.info("Qdrant client initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}", exc_info=True)
            raise

    async def initialize(self):
        """Initialize Qdrant client and create collection if needed"""
        self._ensure_initialized()

    async def add_documents(
        self,
        embeddings: List[List[float]],
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Add documents to vector store

        Args:
            embeddings: List of embedding vectors
            texts: List of document texts
            metadatas: List of metadata dicts
            ids: Optional list of IDs (will generate if not provided)

        Returns:
            List of document IDs
        """
        # Ensure client is initialized
        self._ensure_initialized()
        
        if not ids:
            ids = [str(uuid.uuid4()) for _ in range(len(embeddings))]

        points = []
        for i, (embedding, text, metadata) in enumerate(zip(embeddings, texts, metadatas)):
            payload = {
                "text": text,
                "created_at": datetime.utcnow().isoformat(),
                **metadata
            }

            points.append(
                PointStruct(
                    id=ids[i],
                    vector=embedding,
                    payload=payload,
                )
            )

        # Batch upload
        logger.info(f"Uploading {len(points)} points to Qdrant...")
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )

        logger.info(f"✓ Added {len(points)} documents to vector store")
        return ids

    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents

        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            filters: Metadata filters
            score_threshold: Minimum similarity score

        Returns:
            List of search results with scores and metadata
        """
        # Ensure client is initialized
        self._ensure_initialized()
        
        # Build filter conditions
        filter_conditions = None
        if filters:
            filter_conditions = self._build_filter(filters)

        # Search
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            query_filter=filter_conditions,
            score_threshold=score_threshold,
        )

        # Format results
        formatted_results = []
        for result in results:
            formatted_results.append({
                "id": result.id,
                "score": result.score,
                "text": result.payload.get("text", ""),
                "metadata": {k: v for k, v in result.payload.items() if k != "text"},
            })

        return formatted_results

    def _build_filter(self, filters: Dict[str, Any]) -> Filter:
        """Build Qdrant filter from dict"""
        must_conditions = []

        for key, value in filters.items():
            if isinstance(value, dict):
                # Range filter (e.g., {"year": {"gte": 2020, "lte": 2023}})
                if "gte" in value or "lte" in value:
                    must_conditions.append(
                        FieldCondition(
                            key=key,
                            range=Range(
                                gte=value.get("gte"),
                                lte=value.get("lte"),
                            )
                        )
                    )
            elif isinstance(value, list):
                # Multiple values (OR condition)
                for v in value:
                    must_conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=v),
                        )
                    )
            else:
                # Exact match
                must_conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value),
                    )
                )

        return Filter(must=must_conditions) if must_conditions else None

    async def get_by_ids(self, ids: List[str]) -> List[Dict[str, Any]]:
        """Retrieve documents by IDs"""
        # Ensure client is initialized
        self._ensure_initialized()
        
        results = self.client.retrieve(
            collection_name=self.collection_name,
            ids=ids,
        )

        return [
            {
                "id": r.id,
                "text": r.payload.get("text", ""),
                "metadata": {k: v for k, v in r.payload.items() if k != "text"},
            }
            for r in results
        ]

    async def delete(self, ids: List[str]):
        """Delete documents by IDs"""
        # Ensure client is initialized
        self._ensure_initialized()
        
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=ids,
        )
        logger.info(f"Deleted {len(ids)} documents from vector store")

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count documents matching filters"""
        # Ensure client is initialized
        self._ensure_initialized()
        
        filter_conditions = self._build_filter(filters) if filters else None

        count = self.client.count(
            collection_name=self.collection_name,
            count_filter=filter_conditions,
        )
        return count.count

    async def update_payload(self, id: str, payload: Dict[str, Any]):
        """Update document metadata"""
        # Ensure client is initialized
        self._ensure_initialized()
        
        self.client.set_payload(
            collection_name=self.collection_name,
            payload=payload,
            points=[id],
        )


# Singleton instance
_vector_store = None


def get_vector_store() -> VectorStore:
    """Get vector store singleton"""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store