import httpx
from typing import Dict, Any, List, Optional
import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class CognitaClient:
    """
    Client for Cognita API
    Use Cognita for: Document parsing, chunking, initial indexing
    Use Custom code for: Legal metadata, search, RAG
    """
    
    def __init__(self):
        self.base_url = settings.COGNITA_API_URL
        self.client = httpx.AsyncClient(timeout=300.0)  # 5 min timeout
        
    async def create_collection(
        self,
        collection_name: str,
        embedder_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a collection in Cognita
        
        Args:
            collection_name: Name of collection (e.g., 'supreme_court_judgments')
            embedder_config: Override default embedder
        """
        try:
            if not embedder_config:
                embedder_config = {
                    "provider": "sentence-transformers",
                    "model": settings.EMBEDDING_MODEL_NAME,
                    "embedding_dims": settings.EMBEDDING_DIMENSION,
                }
            
            response = await self.client.post(
                f"{self.base_url}/v1/collections",
                json={
                    "name": collection_name,
                    "description": f"Legal documents collection: {collection_name}",
                    "embedder_config": embedder_config,
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✓ Created collection: {collection_name}")
                return result
            else:
                logger.error(f"Failed to create collection: {response.text}")
                raise Exception(f"Cognita API error: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            raise
    
    async def upload_document(
        self,
        file_path: str,
        collection_name: str,
        document_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Upload document to Cognita for parsing and indexing
        
        Args:
            file_path: Path to PDF/DOCX file
            collection_name: Target collection
            document_metadata: Optional metadata to attach
            
        Returns:
            Parsed document with Cognita's metadata
        """
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            
            logger.info(f"Uploading to Cognita: {file_path.name}")
            
            # Prepare multipart form data
            with open(file_path, 'rb') as f:
                files = {
                    'file': (file_path.name, f, 'application/pdf')
                }
                
                data = {
                    'collection_name': collection_name,
                }
                
                if document_metadata:
                    data['metadata'] = document_metadata
                
                response = await self.client.post(
                    f"{self.base_url}/v1/collections/{collection_name}/documents",
                    files=files,
                    data=data
                )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✓ Cognita parsed: {file_path.name} - {result.get('num_chunks', 0)} chunks")
                return result
            else:
                logger.error(f"Upload failed: {response.text}")
                raise Exception(f"Cognita upload error: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Error uploading document: {e}")
            raise
    
    async def get_document(
        self,
        document_id: str,
        collection_name: str,
    ) -> Dict[str, Any]:
        """Get document details from Cognita"""
        try:
            response = await self.client.get(
                f"{self.base_url}/v1/collections/{collection_name}/documents/{document_id}"
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Document not found: {document_id}")
        
        except Exception as e:
            logger.error(f"Error fetching document: {e}")
            raise
    
    async def list_collections(self) -> List[Dict[str, Any]]:
        """List all collections in Cognita"""
        try:
            response = await self.client.get(f"{self.base_url}/v1/collections")
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception("Failed to list collections")
        
        except Exception as e:
            logger.error(f"Error listing collections: {e}")
            raise
    
    async def delete_document(
        self,
        document_id: str,
        collection_name: str,
    ):
        """Delete document from Cognita"""
        try:
            response = await self.client.delete(
                f"{self.base_url}/v1/collections/{collection_name}/documents/{document_id}"
            )
            
            if response.status_code == 200:
                logger.info(f"✓ Deleted document: {document_id}")
            else:
                raise Exception(f"Failed to delete: {response.text}")
        
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            raise
    
    async def health_check(self) -> bool:
        """Check if Cognita is healthy"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except:
            return False


# Singleton instance
_cognita_client = None


def get_cognita_client() -> CognitaClient:
    """Get Cognita client singleton"""
    global _cognita_client
    if _cognita_client is None:
        _cognita_client = CognitaClient()
    return _cognita_client