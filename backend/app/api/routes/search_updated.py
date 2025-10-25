"""
Search API Routes using LlamaIndex
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import logging
from app.services.llamaindex_service import get_llamaindex_rag

router = APIRouter(prefix="/api/v1/search", tags=["search"])
logger = logging.getLogger(__name__)


# === REQUEST MODELS (Accept JSON Body) ===
class SearchRequest(BaseModel):
    """Request model for search with answer"""
    query: str = Field(..., description="Legal question to search", min_length=3)
    top_k: int = Field(5, ge=1, le=20, description="Number of sources to retrieve")


class RetrieveRequest(BaseModel):
    """Request model for retrieval only"""
    query: str = Field(..., description="Search query", min_length=3)
    top_k: int = Field(10, ge=1, le=50, description="Number of documents")


# Initialize LlamaIndex on module load
rag = get_llamaindex_rag()
try:
    rag.initialize()
    logger.info("✅ LlamaIndex initialized for search API")
except Exception as e:
    logger.error(f"❌ Failed to initialize LlamaIndex: {e}")


@router.post("/query")
async def search_with_answer(request: SearchRequest) -> Dict[str, Any]:
    """
    Search legal documents and generate AI answer using LlamaIndex
    
    **Example Request:**
```json
    {
        "query": "What are the provisions for anticipatory bail?",
        "top_k": 5
    }
```
    
    **Returns:**
    - AI-generated answer
    - Source documents with metadata
    - Relevance scores
    """
    try:
        logger.info(f"📝 Query received: '{request.query}' (top_k={request.top_k})")
        
        # Use LlamaIndex for search and answer
        result = await rag.search_and_answer(query=request.query, top_k=request.top_k)
        
        # Format response
        return {
            "success": True,
            "query": request.query,
            "answer": result.get("answer", ""),
            "sources": result.get("sources", []),
            "source_count": result.get("source_count", 0),
            "engine": "llamaindex"
        }
        
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retrieve")
async def retrieve_only(request: RetrieveRequest) -> Dict[str, Any]:
    """
    Retrieve relevant documents without generating answer (faster)
    
    **Example Request:**
```json
    {
        "query": "Section 438 CrPC",
        "top_k": 10
    }
```
    
    **Use this for:**
    - Document browsing
    - Quick searches
    - Building context for drafting
    """
    try:
        logger.info(f"🔍 Retrieval query: '{request.query}' (top_k={request.top_k})")
        
        # Retrieve without generating answer
        results = await rag.search_only(query=request.query, top_k=request.top_k)
        
        return {
            "success": True,
            "query": request.query,
            "results": results,
            "count": len(results)
        }
        
    except Exception as e:
        logger.error(f"Retrieval failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Check if search service is healthy"""
    try:
        if rag._initialized:
            return {
                "status": "healthy",
                "service": "search",
                "engine": "llamaindex",
                "initialized": True
            }
        else:
            rag.initialize()
            return {
                "status": "healthy",
                "service": "search",
                "engine": "llamaindex",
                "initialized": True,
                "message": "Just initialized"
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "search",
            "error": str(e),
            "initialized": False
        }


@router.get("/stats")
async def get_search_stats():
    """Get search engine statistics"""
    try:
        from qdrant_client import QdrantClient
        from app.core.config import settings
        
        client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT
        )
        
        info = client.get_collection("legal_documents")
        
        return {
            "vector_store": "qdrant",
            "collection": "legal_documents",
            "total_documents": info.points_count,
            "embedding_model": "nlpaueb/legal-bert-base-uncased",
            "llm_provider": "groq",
            "llm_model": "llama-3.3-70b-versatile"
        }
        
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return {
            "error": str(e),
            "message": "Could not retrieve statistics"
        }