from sentence_transformers import SentenceTransformer
from typing import List, Union
import numpy as np
import logging
import asyncio

from app.core.config import settings

logger = logging.getLogger(__name__)


class Embedder:
    """Embedding generation service"""
    
    _model_loaded = False
    
    def __init__(self):
        self.model = None
        self.model_name = settings.EMBEDDING_MODEL_NAME
        
    async def load_model(self):
        """Load embedding model"""
        if self._model_loaded and self.model is not None:
            logger.info("Model already loaded")
            return
            
        try:
            logger.info(f"Loading embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            self._model_loaded = True
            Embedder._model_loaded = True
            logger.info(f"✓ Model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    
    def _ensure_model_loaded(self):
        """Ensure model is loaded before use"""
        if self.model is None:
            logger.warning("Model not loaded, loading synchronously...")
            # Load synchronously as a fallback
            self.model = SentenceTransformer(self.model_name)
            self._model_loaded = True
            Embedder._model_loaded = True
            logger.info("✓ Model loaded successfully (sync)")
    
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for single text"""
        self._ensure_model_loaded()
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def embed_texts(self, texts: List[str], batch_size: int = None) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        self._ensure_model_loaded()
        
        if batch_size is None:
            batch_size = settings.EMBEDDING_BATCH_SIZE
        
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
        )
        
        return embeddings.tolist()
    
    def compute_similarity(
        self, 
        embedding1: Union[List[float], np.ndarray],
        embedding2: Union[List[float], np.ndarray]
    ) -> float:
        """Compute cosine similarity between two embeddings"""
        if isinstance(embedding1, list):
            embedding1 = np.array(embedding1)
        if isinstance(embedding2, list):
            embedding2 = np.array(embedding2)
        
        similarity = np.dot(embedding1, embedding2) / (
            np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
        )
        return float(similarity)


# Global singleton instance
_embedder = None


def get_embedder() -> Embedder:
    """Get embedder singleton"""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder