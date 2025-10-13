from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import logging

from app.core.config import settings, validate_settings
from app.api.endpoints import search, documents, upload, analytics

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validate configuration on startup
validate_settings()

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Legal RAG System API for Indian Legal Professionals",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "app": settings.APP_NAME
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Legal RAG System API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health"
    }


# Include routers
app.include_router(
    search.router,
    prefix=f"{settings.API_V1_PREFIX}/search",
    tags=["Search & Retrieval"]
)

app.include_router(
    documents.router,
    prefix=f"{settings.API_V1_PREFIX}/documents",
    tags=["Documents"]
)

app.include_router(
    upload.router,
    prefix=f"{settings.API_V1_PREFIX}/upload",
    tags=["Upload"]
)

app.include_router(
    analytics.router,
    prefix=f"{settings.API_V1_PREFIX}/analytics",
    tags=["Analytics"]
)


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting Legal RAG System (Hybrid Mode)...")
    
    # Check Cognita health
    if settings.USE_COGNITA_FOR_PARSING:
        from app.services.cognita.client import get_cognita_client
        cognita_client = get_cognita_client()
        
        is_healthy = await cognita_client.health_check()
        if is_healthy:
            logger.info("✓ Cognita is running and healthy")
            
            # Create default collection if needed
            try:
                collections = await cognita_client.list_collections()
                if not any(c.get('name') == 'legal_documents' for c in collections):
                    await cognita_client.create_collection('legal_documents')
                    logger.info("✓ Created default 'legal_documents' collection")
            except Exception as e:
                logger.warning(f"Could not check/create collections: {e}")
        else:
            logger.warning("⚠️  Cognita is not responding. Document parsing will use fallback.")
    
    # Initialize vector database connection (direct access for search)
    from app.services.embedding.vector_store import VectorStore
    vector_store = VectorStore()
    await vector_store.initialize()
    logger.info("✓ Direct Qdrant connection established (for custom search)")
    
    # Initialize embedding model (for query embeddings)
    from app.services.embedding.embedder import Embedder
    embedder = Embedder()
    await embedder.load_model()
    logger.info(f"✓ Embedding model loaded: {settings.EMBEDDING_MODEL_NAME}")
    
    # Initialize LLM client
    from app.services.llm.client import LLMClient
    llm_client = LLMClient()
    logger.info(f"✓ LLM client initialized: {settings.DEFAULT_LLM_PROVIDER}")
    
    logger.info("=" * 60)
    logger.info("HYBRID MODE ACTIVE:")
    logger.info("  - Cognita: Document parsing & indexing")
    logger.info("  - Custom: Legal metadata, search, RAG")
    logger.info("=" * 60)
    logger.info("✓ Legal RAG System started successfully!")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Legal RAG System...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )