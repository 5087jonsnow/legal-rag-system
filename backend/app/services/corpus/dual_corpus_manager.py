# ============================================================
# FILE: backend/app/services/corpus/dual_corpus_manager.py
# PURPOSE: Manage dual corpus architecture (public + private documents)
# ============================================================

from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
    PointStruct,
)
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.schema import Document as LlamaDocument

from app.core.config import settings

logger = logging.getLogger(__name__)


class DualCorpusManager:
    """
    Manage dual corpus architecture for legal documents.

    Architecture:
    1. PUBLIC corpus: Shared legal documents (SC/HC judgments, statutes)
       - Collection: "public_legal_corpus"
       - Accessible to all users
       - Admin-only write access

    2. PRIVATE corpus: User/org-specific documents
       - Collection: "private_user_corpus"
       - Filtered by org_id in metadata
       - User upload access

    Search strategy:
    - Search BOTH corpora
    - Filter private by org_id
    - Merge and rerank results
    """

    PUBLIC_COLLECTION = "public_legal_corpus"
    PRIVATE_COLLECTION = "private_user_corpus"

    def __init__(self):
        """Initialize dual corpus manager with Qdrant client"""
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT
        )

        logger.info(
            f"DualCorpusManager initialized: "
            f"Public={self.PUBLIC_COLLECTION}, Private={self.PRIVATE_COLLECTION}"
        )

    async def search_both(
        self,
        query_embedding: List[float],
        user_id: str,
        org_id: str,
        top_k_public: int = 5,
        top_k_private: int = 3,
        score_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Search both public and private corpora, merge results.

        Args:
            query_embedding: Query vector
            user_id: User ID (for logging/analytics)
            org_id: Organization ID (for filtering private docs)
            top_k_public: Number of public docs to retrieve
            top_k_private: Number of private docs to retrieve
            score_threshold: Minimum similarity score

        Returns:
            Merged and sorted results from both corpora
        """
        results = []

        # 1. Search public corpus (no filtering)
        try:
            public_results = self.client.search(
                collection_name=self.PUBLIC_COLLECTION,
                query_vector=query_embedding,
                limit=top_k_public,
                score_threshold=score_threshold
            )

            for result in public_results:
                results.append({
                    "id": str(result.id),
                    "score": result.score,
                    "text": result.payload.get("text", ""),
                    "metadata": {
                        **{k: v for k, v in result.payload.items() if k != "text"},
                        "corpus": "public"
                    }
                })

            logger.info(f"Found {len(public_results)} results in public corpus")

        except Exception as e:
            logger.error(f"Public corpus search failed: {e}", exc_info=True)

        # 2. Search private corpus (filter by org_id)
        try:
            private_filter = Filter(
                must=[
                    FieldCondition(
                        key="org_id",
                        match=MatchValue(value=org_id)
                    )
                ]
            )

            private_results = self.client.search(
                collection_name=self.PRIVATE_COLLECTION,
                query_vector=query_embedding,
                query_filter=private_filter,
                limit=top_k_private,
                score_threshold=score_threshold
            )

            for result in private_results:
                results.append({
                    "id": str(result.id),
                    "score": result.score,
                    "text": result.payload.get("text", ""),
                    "metadata": {
                        **{k: v for k, v in result.payload.items() if k != "text"},
                        "corpus": "private"
                    }
                })

            logger.info(f"Found {len(private_results)} results in private corpus (org={org_id})")

        except Exception as e:
            logger.error(f"Private corpus search failed: {e}", exc_info=True)

        # 3. Sort merged results by score
        results.sort(key=lambda x: x["score"], reverse=True)

        logger.info(
            f"Dual corpus search complete: {len(results)} total results "
            f"(user={user_id}, org={org_id})"
        )

        return results

    async def add_to_public(
        self,
        documents: List[Dict[str, Any]],
        embeddings: List[List[float]]
    ) -> List[str]:
        """
        Add documents to public corpus (admin only).

        Args:
            documents: List of documents with text and metadata
            embeddings: Corresponding embeddings

        Returns:
            List of document IDs
        """
        if len(documents) != len(embeddings):
            raise ValueError("Documents and embeddings length mismatch")

        points = []
        doc_ids = []

        for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
            doc_id = doc.get("id") or f"pub_{datetime.utcnow().timestamp()}_{i}"
            doc_ids.append(doc_id)

            payload = {
                "text": doc.get("text", ""),
                "created_at": datetime.utcnow().isoformat(),
                "corpus": "public",
                **doc.get("metadata", {})
            }

            points.append(
                PointStruct(
                    id=doc_id,
                    vector=embedding,
                    payload=payload
                )
            )

        # Upsert to public collection
        self.client.upsert(
            collection_name=self.PUBLIC_COLLECTION,
            points=points
        )

        logger.info(f"Added {len(points)} documents to public corpus")
        return doc_ids

    async def add_to_private(
        self,
        documents: List[Dict[str, Any]],
        embeddings: List[List[float]],
        org_id: str,
        user_id: str
    ) -> List[str]:
        """
        Add documents to private corpus (user upload).

        Args:
            documents: List of documents with text and metadata
            embeddings: Corresponding embeddings
            org_id: Organization ID (for filtering)
            user_id: User ID (for audit trail)

        Returns:
            List of document IDs
        """
        if len(documents) != len(embeddings):
            raise ValueError("Documents and embeddings length mismatch")

        points = []
        doc_ids = []

        for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
            doc_id = doc.get("id") or f"priv_{org_id}_{datetime.utcnow().timestamp()}_{i}"
            doc_ids.append(doc_id)

            payload = {
                "text": doc.get("text", ""),
                "created_at": datetime.utcnow().isoformat(),
                "corpus": "private",
                "org_id": org_id,  # CRITICAL: For filtering
                "uploaded_by": user_id,
                **doc.get("metadata", {})
            }

            points.append(
                PointStruct(
                    id=doc_id,
                    vector=embedding,
                    payload=payload
                )
            )

        # Upsert to private collection
        self.client.upsert(
            collection_name=self.PRIVATE_COLLECTION,
            points=points
        )

        logger.info(
            f"Added {len(points)} documents to private corpus "
            f"(org={org_id}, user={user_id})"
        )
        return doc_ids

    async def delete_from_private(
        self,
        doc_ids: List[str],
        org_id: str,
        user_id: str
    ) -> int:
        """
        Delete documents from private corpus.

        Security: Only allow deletion if org_id matches.

        Args:
            doc_ids: Document IDs to delete
            org_id: Organization ID (must match)
            user_id: User ID (for audit)

        Returns:
            Number of documents deleted
        """
        # Verify ownership before deletion
        verified_ids = []

        for doc_id in doc_ids:
            try:
                points = self.client.retrieve(
                    collection_name=self.PRIVATE_COLLECTION,
                    ids=[doc_id]
                )

                if points:
                    point = points[0]
                    if point.payload.get("org_id") == org_id:
                        verified_ids.append(doc_id)
                    else:
                        logger.warning(
                            f"Delete blocked: doc {doc_id} not owned by org {org_id}"
                        )

            except Exception as e:
                logger.error(f"Error verifying doc {doc_id}: {e}")

        # Delete verified docs
        if verified_ids:
            self.client.delete(
                collection_name=self.PRIVATE_COLLECTION,
                points_selector=verified_ids
            )

            logger.info(
                f"Deleted {len(verified_ids)} documents from private corpus "
                f"(org={org_id}, user={user_id})"
            )

        return len(verified_ids)

    async def count_docs(
        self,
        corpus: str = "both",
        org_id: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Count documents in corpus/corpora.

        Args:
            corpus: "public", "private", or "both"
            org_id: Organization ID (for private corpus count)

        Returns:
            Dict with counts
        """
        counts = {}

        if corpus in ["public", "both"]:
            try:
                result = self.client.count(
                    collection_name=self.PUBLIC_COLLECTION
                )
                counts["public"] = result.count
            except Exception as e:
                logger.error(f"Error counting public corpus: {e}")
                counts["public"] = 0

        if corpus in ["private", "both"]:
            try:
                if org_id:
                    # Count for specific org
                    filter_condition = Filter(
                        must=[
                            FieldCondition(
                                key="org_id",
                                match=MatchValue(value=org_id)
                            )
                        ]
                    )
                    result = self.client.count(
                        collection_name=self.PRIVATE_COLLECTION,
                        count_filter=filter_condition
                    )
                else:
                    # Count all private docs
                    result = self.client.count(
                        collection_name=self.PRIVATE_COLLECTION
                    )

                counts["private"] = result.count
            except Exception as e:
                logger.error(f"Error counting private corpus: {e}")
                counts["private"] = 0

        return counts

    async def get_user_docs(
        self,
        org_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get list of user's private documents (for document management UI).

        Args:
            org_id: Organization ID
            limit: Max results
            offset: Pagination offset

        Returns:
            List of document metadata
        """
        filter_condition = Filter(
            must=[
                FieldCondition(
                    key="org_id",
                    match=MatchValue(value=org_id)
                )
            ]
        )

        scroll_result = self.client.scroll(
            collection_name=self.PRIVATE_COLLECTION,
            scroll_filter=filter_condition,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False
        )

        points = scroll_result[0]

        docs = []
        for point in points:
            docs.append({
                "id": str(point.id),
                "text_preview": point.payload.get("text", "")[:200] + "...",
                "metadata": {
                    k: v for k, v in point.payload.items()
                    if k != "text"
                },
                "created_at": point.payload.get("created_at"),
                "uploaded_by": point.payload.get("uploaded_by")
            })

        return docs


# Singleton instance
_dual_corpus_manager = None

def get_dual_corpus_manager() -> DualCorpusManager:
    """Get or create dual corpus manager singleton"""
    global _dual_corpus_manager
    if _dual_corpus_manager is None:
        _dual_corpus_manager = DualCorpusManager()
    return _dual_corpus_manager


# End of file
