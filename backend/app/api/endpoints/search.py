from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import time
import logging

from app.services.embedding.embedder import get_embedder
from app.services.embedding.vector_store import get_vector_store
from app.services.llm.client import get_llm_client

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response models
class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    top_k: int = Field(5, description="Number of results", ge=1, le=50)
    filters: Optional[Dict[str, Any]] = Field(None, description="Metadata filters")
    include_answer: bool = Field(True, description="Generate LLM answer")
    
    class Config:
        schema_extra = {
            "example": {
                "query": "What is the latest Supreme Court position on anticipatory bail?",
                "top_k": 5,
                "filters": {"court_level": "Supreme Court", "year": {"gte": 2020}},
                "include_answer": True
            }
        }


class SearchResult(BaseModel):
    id: str
    text: str
    score: float
    metadata: Dict[str, Any]


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    answer: Optional[str] = None
    citations: Optional[List[Dict[str, Any]]] = None
    latency_ms: int
    num_results: int


@router.post("/", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Search for relevant legal documents
    
    HYBRID APPROACH:
    - Cognita indexed documents in Qdrant
    - We use CUSTOM search logic (not Cognita's generic search)
    - We apply legal-specific filters and reranking
    - We generate answers with legal-specific prompts
    
    This gives us:
    - Fast indexing (Cognita)
    - Smart retrieval (our custom logic)
    - Legal accuracy (our domain knowledge)
    """
    start_time = time.time()
    
    try:
        # Get services
        embedder = get_embedder()
        vector_store = get_vector_store()
        llm_client = get_llm_client()
        
        # Generate query embedding
        logger.info(f"Generating embedding for query: {request.query}")
        query_embedding = embedder.embed_text(request.query)
        
        # Use OUR custom search (not Cognita's generic search)
        # This is where legal intelligence happens
        logger.info(f"Searching vector store with filters: {request.filters}")
        results = await vector_store.search(
            query_embedding=query_embedding,
            top_k=request.top_k,
            filters=request.filters,
            score_threshold=0.5,  # Minimum similarity
        )
        
        logger.info(f"Found {len(results)} results")
        
        # Format results
        search_results = [
            SearchResult(
                id=r["id"],
                text=r["text"],
                score=r["score"],
                metadata=r["metadata"]
            )
            for r in results
        ]
        
        # Generate answer with LEGAL-SPECIFIC prompts
        answer = None
        citations = None
        
        if request.include_answer and results:
            logger.info("Generating answer with LLM")
            rag_response = await llm_client.generate_with_context(
                query=request.query,
                context_docs=results,
            )
            answer = rag_response["answer"]
            citations = rag_response["citations"]
            logger.info(f"Generated answer with {len(citations)} citations")
        
        latency_ms = int((time.time() - start_time) * 1000)
        logger.info(f"Search completed in {latency_ms}ms")
        
        return SearchResponse(
            query=request.query,
            results=search_results,
            answer=answer,
            citations=citations,
            latency_ms=latency_ms,
            num_results=len(search_results)
        )
    
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/similar/{document_id}")
async def find_similar(
    document_id: str,
    top_k: int = 5,
):
    """Find documents similar to a given document"""
    try:
        logger.info(f"Finding similar documents to: {document_id}")
        vector_store = get_vector_store()
        
        # Get the document
        docs = await vector_store.get_by_ids([document_id])
        if not docs:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # TODO: Implement similar document search
        # This would require storing document embeddings or regenerating them
        
        return {
            "document_id": document_id,
            "similar_documents": [],
            "message": "Similar document search coming soon"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Similar search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
async def batch_search(queries: List[str], top_k: int = 5):
    """
    Search multiple queries at once
    
    Useful for finding related information across multiple questions
    """
    try:
        logger.info(f"Processing batch search for {len(queries)} queries")
        
        results = []
        for query in queries:
            try:
                response = await search(
                    SearchRequest(
                        query=query,
                        top_k=top_k,
                        include_answer=False  # Skip answer generation for batch
                    )
                )
                results.append({
                    "query": query,
                    "results": response.results,
                    "num_results": response.num_results
                })
            except Exception as e:
                logger.error(f"Failed to process query '{query}': {e}")
                results.append({
                    "query": query,
                    "error": str(e)
                })
        
        return {
            "total_queries": len(queries),
            "successful": len([r for r in results if "error" not in r]),
            "results": results
        }
    
    except Exception as e:
        logger.error(f"Batch search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))