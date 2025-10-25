from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings with Docker-appropriate defaults"""
    
    # Application
    APP_NAME: str = "Legal RAG System"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    
    # Cognita Integration
    COGNITA_API_URL: str = "http://localhost:8000"
    USE_COGNITA_FOR_PARSING: bool = True
    USE_CUSTOM_SEARCH: bool = True  # Use our legal-specific search
    USE_CUSTOM_RAG: bool = True  # Use our legal-specific RAG
    
    # Database - FIXED for Docker
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://legal_user:legal_pass@postgres:5432/legal_rag_db"
    )
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    
    # Vector Database (Qdrant) - FIXED for Docker
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "qdrant")  # Changed from localhost
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
    QDRANT_COLLECTION_NAME: str = "legal_documents"
    QDRANT_API_KEY: Optional[str] = None
    
    # Object Storage (MinIO) - FIXED for Docker
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "minio:9000")  # Changed
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ROOT_USER", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
    MINIO_BUCKET_NAME: str = "legal-documents"
    MINIO_SECURE: bool = False
    
    # Redis Cache - FIXED for Docker
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")  # Changed from localhost
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    CACHE_TTL: int = 3600  # 1 hour
    
    # LLM APIs - Load from environment
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY", None)
   GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY") 
    COHERE_API_KEY: Optional[str] = os.getenv("COHERE_API_KEY", None)
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY", None)
    
    # Embedding Model
    EMBEDDING_MODEL_NAME: str = "nlpaueb/legal-bert-base-uncased"
    EMBEDDING_DIMENSION: int = 768
    EMBEDDING_BATCH_SIZE: int = 32
    
    # Retrieval Settings
    TOP_K_RETRIEVAL: int = 10  # Initial retrieval
    TOP_K_RERANK: int = 5      # After reranking
    MIN_SIMILARITY_SCORE: float = 0.5
    USE_RERANKING: bool = False  # Disabled until we have Cohere key
    RERANKING_MODEL: str = "cohere"  # cohere or cross-encoder
    
    # LLM Settings
    DEFAULT_LLM_PROVIDER: str = "groq"
    DEFAULT_LLM_MODEL: str = "llama-3.3-70b-versatile"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2048
    LLM_TIMEOUT: int = 60
    
    # Chunking Strategy
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    
    # Document Processing
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list = [".pdf", ".docx", ".txt", ".html"]
    OCR_ENABLED: bool = True
    
    # Security
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "your-secret-key-change-in-production-" + os.urandom(16).hex()
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000
    
    # Monitoring
    ENABLE_METRICS: bool = True
    SENTRY_DSN: Optional[str] = None
    LOG_LEVEL: str = "INFO"
    
    # Feature Flags
    ENABLE_DOCUMENT_DRAFTING: bool = True
    ENABLE_CONTRACT_REVIEW: bool = True
    ENABLE_CASE_PREDICTION: bool = False  # Coming soon
    ENABLE_CITATION_GRAPH: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Singleton instance
settings = Settings()


# Validate critical settings on startup
def validate_settings():
    """Validate that critical settings are configured"""
    errors = []
    
    if not settings.GROQ_API_KEY and not settings.OPENAI_API_KEY:
        errors.append("At least one LLM API key must be configured (GROQ_API_KEY or OPENAI_API_KEY)")
    
    if settings.USE_RERANKING and settings.RERANKING_MODEL == "cohere" and not settings.COHERE_API_KEY:
        # Don't error, just disable reranking
        settings.USE_RERANKING = False
        print("⚠️  Cohere reranking disabled (no API key)")
    
    if errors:
        raise ValueError(f"Configuration errors:\n" + "\n".join(f"- {e}" for e in errors))
    
    print(f"✓ Configuration validated successfully")
    print(f"✓ Using LLM: {settings.DEFAULT_LLM_PROVIDER}/{settings.DEFAULT_LLM_MODEL}")
    print(f"✓ Embedding model: {settings.EMBEDDING_MODEL_NAME}")
    print(f"✓ Vector DB: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
    print(f"✓ Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'configured'}")


if __name__ == "__main__":
    validate_settings()