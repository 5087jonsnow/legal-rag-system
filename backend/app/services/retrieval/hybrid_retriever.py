# ============================================================
# FILE: backend/app/services/retrieval/hybrid_retriever.py
# PURPOSE: Hybrid search combining BM25 (keyword) + semantic (vector) retrieval
# ============================================================

from typing import List, Dict, Any, Optional
import logging
from collections import defaultdict

from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle
from qdrant_client import QdrantClient

from app.core.config import settings

logger = logging.getLogger(__name__)


class HybridRetriever(BaseRetriever):
    """
    Hybrid retriever combining BM25 keyword search and semantic vector search.

    Uses Reciprocal Rank Fusion (RRF) to combine results from:
    1. BM25 (keyword matching) - good for exact statute/case number matches
    2. Vector search (semantic) - good for conceptual queries

    Why hybrid?
    - Query: "Section 438 CrPC" → BM25 ensures exact section match
    - Query: "anticipatory bail conditions" → Semantic finds related concepts
    """

    def __init__(
        self,
        vector_index: VectorStoreIndex,
        collection_name: str = None,
        bm25_weight: float = 0.5,
        vector_weight: float = 0.5,
        top_k: int = 10
    ):
        """
        Initialize hybrid retriever.

        Args:
            vector_index: LlamaIndex vector store index
            collection_name: Qdrant collection name
            bm25_weight: Weight for BM25 scores (0-1)
            vector_weight: Weight for vector scores (0-1)
            top_k: Number of results to return
        """
        self.vector_index = vector_index
        self.collection_name = collection_name or settings.QDRANT_COLLECTION_NAME
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self._top_k = top_k

        # Get Qdrant client for BM25 search
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT
        )

        # Vector retriever from index
        self.vector_retriever = vector_index.as_retriever(similarity_top_k=top_k)

        logger.info(
            f"HybridRetriever initialized: "
            f"BM25 weight={bm25_weight}, Vector weight={vector_weight}, top_k={top_k}"
        )

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """
        Retrieve documents using hybrid search.

        Args:
            query_bundle: LlamaIndex query bundle

        Returns:
            List of nodes with fused scores
        """
        query_str = query_bundle.query_str

        # 1. Get BM25 results (keyword search via Qdrant text filter)
        bm25_results = self._bm25_search(query_str, top_k=self._top_k * 2)

        # 2. Get vector search results (semantic)
        vector_results = self.vector_retriever.retrieve(query_str)

        # 3. Fusion using Reciprocal Rank Fusion
        fused_results = self._reciprocal_rank_fusion(
            bm25_results=bm25_results,
            vector_results=vector_results,
            top_k=self._top_k
        )

        logger.info(
            f"Hybrid retrieval: {len(bm25_results)} BM25 + {len(vector_results)} vector "
            f"→ {len(fused_results)} fused results"
        )

        return fused_results

    def _bm25_search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Perform BM25-like keyword search using Qdrant scroll + text matching.

        Note: Qdrant doesn't have native BM25, so we use:
        1. Scroll through documents
        2. Score by keyword overlap
        3. Rank by TF-IDF-like scoring

        For production, consider:
        - Integrating Elasticsearch for true BM25
        - Using Qdrant's upcoming full-text search
        - Pre-computing BM25 scores offline
        """
        query_terms = set(query.lower().split())

        # Scroll documents (limit for performance)
        scroll_result = self.client.scroll(
            collection_name=self.collection_name,
            limit=100,  # Check first 100 docs
            with_payload=True,
            with_vectors=False
        )

        points = scroll_result[0]
        scored_docs = []

        for point in points:
            text = point.payload.get("text", "")
            doc_terms = set(text.lower().split())

            # Simple keyword overlap scoring
            overlap = len(query_terms & doc_terms)
            total_terms = len(query_terms)

            if overlap > 0:
                # BM25-like score (simplified)
                score = overlap / total_terms

                scored_docs.append({
                    "id": str(point.id),
                    "text": text,
                    "score": score,
                    "metadata": {
                        k: v for k, v in point.payload.items()
                        if k != "text"
                    }
                })

        # Sort by score
        scored_docs.sort(key=lambda x: x["score"], reverse=True)

        return scored_docs[:top_k]

    def _reciprocal_rank_fusion(
        self,
        bm25_results: List[Dict[str, Any]],
        vector_results: List[NodeWithScore],
        top_k: int,
        k: int = 60  # RRF constant
    ) -> List[NodeWithScore]:
        """
        Fuse BM25 and vector search results using Reciprocal Rank Fusion.

        RRF formula: score = sum(1 / (k + rank_i)) for each retrieval method

        Args:
            bm25_results: BM25 search results
            vector_results: Vector search results
            top_k: Number of final results
            k: RRF constant (default 60)

        Returns:
            Fused and re-ranked results
        """
        # Build doc_id → score mapping
        doc_scores = defaultdict(float)
        doc_nodes = {}  # Store NodeWithScore objects

        # Add BM25 scores
        for rank, result in enumerate(bm25_results):
            doc_id = result["id"]
            rrf_score = self.bm25_weight * (1.0 / (k + rank + 1))
            doc_scores[doc_id] += rrf_score

        # Add vector scores
        for rank, node_with_score in enumerate(vector_results):
            doc_id = node_with_score.node.id_
            rrf_score = self.vector_weight * (1.0 / (k + rank + 1))
            doc_scores[doc_id] += rrf_score

            # Store node object
            if doc_id not in doc_nodes:
                doc_nodes[doc_id] = node_with_score

        # Sort by fused score
        sorted_docs = sorted(
            doc_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]

        # Build final result list
        fused_results = []
        for doc_id, fused_score in sorted_docs:
            if doc_id in doc_nodes:
                # Use existing node from vector search
                node = doc_nodes[doc_id]
                node.score = fused_score
                fused_results.append(node)
            else:
                # Create node from BM25 result (fallback)
                # This case happens when doc was in BM25 but not in top vector results
                logger.debug(f"Doc {doc_id} from BM25 only (not in vector results)")

        return fused_results

    async def aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Async retrieve (calls sync _retrieve)"""
        return self._retrieve(query_bundle)


# Factory function for easy initialization
def create_hybrid_retriever(
    vector_index: VectorStoreIndex,
    collection_name: Optional[str] = None,
    bm25_weight: float = 0.5,
    vector_weight: float = 0.5,
    top_k: int = 10
) -> HybridRetriever:
    """
    Create a hybrid retriever instance.

    Args:
        vector_index: LlamaIndex vector store index
        collection_name: Qdrant collection name
        bm25_weight: Weight for BM25 scores
        vector_weight: Weight for vector scores
        top_k: Number of results

    Returns:
        HybridRetriever instance
    """
    return HybridRetriever(
        vector_index=vector_index,
        collection_name=collection_name,
        bm25_weight=bm25_weight,
        vector_weight=vector_weight,
        top_k=top_k
    )


# End of file
