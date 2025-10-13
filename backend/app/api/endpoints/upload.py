from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import shutil
import os
from pathlib import Path
import uuid
import logging

from app.services.document.processor import get_document_processor
from app.services.embedding.embedder import get_embedder
from app.services.embedding.vector_store import get_vector_store
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()  # ← CRITICAL: DO NOT REMOVE THIS LINE


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    file_size: int
    status: str
    message: str


async def process_uploaded_document(
    file_path: str,
    document_id: str,
    document_type: str,
    collection_name: str = "legal_documents",
):
    """
    Background task to process uploaded document
    
    Direct processing (no Cognita):
    1. Parse PDF with PyMuPDF
    2. Extract legal metadata
    3. Generate embeddings
    4. Store in Qdrant
    """
    try:
        logger.info(f"Processing document {document_id}: {file_path}")
        
        # Use document processor
        processor = get_document_processor()
        result = await processor.process_document(
            file_path=file_path,
            collection_name=collection_name,
            document_type=document_type
        )
        
        # Get chunks
        chunks = result.get('chunks', [])
        if not chunks:
            logger.error(f"No chunks generated for document {document_id}")
            return
        
        # Extract text from chunks
        chunk_texts = []
        for chunk in chunks:
            if isinstance(chunk, dict):
                chunk_texts.append(chunk.get('content', ''))
            elif isinstance(chunk, str):
                chunk_texts.append(chunk)
            else:
                chunk_texts.append(str(chunk))
        
        logger.info(f"Generated {len(chunk_texts)} chunks for document {document_id}")
        
        # Generate embeddings
        embedder = get_embedder()
        embeddings = embedder.embed_texts(chunk_texts)
        
        logger.info(f"Generated {len(embeddings)} embeddings")
        
        # Prepare metadata for each chunk
        base_metadata = result.get('metadata', {})
        chunk_metadatas = []
        for i, chunk_text in enumerate(chunk_texts):
            metadata = {
                **base_metadata,
                'document_id': document_id,
                'chunk_index': i,
                'total_chunks': len(chunk_texts),
                'document_type': document_type,
            }
            chunk_metadatas.append(metadata)
        
        # Store in vector database
        vector_store = get_vector_store()
        chunk_ids = await vector_store.add_documents(
            embeddings=embeddings,
            texts=chunk_texts,
            metadatas=chunk_metadatas,
        )
        
        logger.info(f"✓ Document {document_id} processed successfully")
        logger.info(f"  - Citation: {base_metadata.get('citation', 'N/A')}")
        logger.info(f"  - Court: {base_metadata.get('court_name', 'N/A')}")
        logger.info(f"  - Chunks indexed: {len(chunk_ids)}")
        logger.info(f"  - Precedents: {len(base_metadata.get('precedents_cited', []))}")
        
    except Exception as e:
        logger.error(f"Failed to process document {document_id}: {e}", exc_info=True)


@router.post("/document", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = "judgment",
    collection_name: str = "legal_documents",
    organization_id: Optional[str] = None,
):
    """
    Upload and process a legal document
    
    Args:
        file: PDF, DOCX, or TXT file
        document_type: Type of document (judgment, statute, contract)
        collection_name: Collection name for vector storage
        organization_id: Organization ID (for multi-tenancy)
    """
    try:
        # Validate file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type {file_ext} not supported. Allowed: {settings.ALLOWED_EXTENSIONS}"
            )
        
        # Generate document ID
        document_id = str(uuid.uuid4())
        
        # Save file
        upload_dir = Path("documents/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = upload_dir / f"{document_id}{file_ext}"
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = file_path.stat().st_size
        
        # Validate file size
        max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if file_size > max_size_bytes:
            file_path.unlink()  # Delete file
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {settings.MAX_UPLOAD_SIZE_MB}MB"
            )
        
        # Process in background
        background_tasks.add_task(
            process_uploaded_document,
            str(file_path),
            document_id,
            document_type,
            collection_name,
        )
        
        return UploadResponse(
            document_id=document_id,
            filename=file.filename,
            file_size=file_size,
            status="processing",
            message="Document uploaded. Processing in background."
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{document_id}")
async def get_document_status(document_id: str):
    """Get processing status of uploaded document"""
    try:
        # TODO: Query PostgreSQL for document status
        # For now, return mock response
        return {
            "document_id": document_id,
            "status": "completed",
            "message": "Document processed successfully",
            "chunks_indexed": 42,
        }
    
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
async def batch_upload(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    document_type: str = "judgment",
):
    """Upload multiple documents at once"""
    results = []
    
    for file in files:
        try:
            result = await upload_document(
                background_tasks=background_tasks,
                file=file,
                document_type=document_type,
            )
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to upload {file.filename}: {e}")
            results.append({
                "filename": file.filename,
                "status": "failed",
                "error": str(e)
            })
    
    return {
        "total_files": len(files),
        "successful": sum(1 for r in results if isinstance(r, UploadResponse)),
        "failed": sum(1 for r in results if isinstance(r, dict) and r.get("status") == "failed"),
        "results": results
    }