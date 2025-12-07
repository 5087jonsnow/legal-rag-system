from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
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
from app.services.corpus.dual_corpus_manager import get_dual_corpus_manager
from app.core.config import settings
from app.core.security import get_current_user, get_current_admin_user, User

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
    user_id: str,
    org_id: str,
    is_public: bool = False,
    collection_name: str = "legal_documents",
):
    """
    Background task to process uploaded document with dual corpus routing.

    Processing:
    1. Parse PDF with PyMuPDF
    2. Extract legal metadata
    3. Generate embeddings
    4. Route to PUBLIC or PRIVATE corpus based on is_public flag
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

        # Build documents for dual corpus manager
        documents = []
        for i, chunk_text in enumerate(chunk_texts):
            metadata = {
                **base_metadata,
                'document_id': document_id,
                'chunk_index': i,
                'total_chunks': len(chunk_texts),
                'document_type': document_type,
            }

            documents.append({
                'id': f"{document_id}_chunk_{i}",
                'text': chunk_text,
                'metadata': metadata
            })

        # Route to appropriate corpus
        corpus_manager = get_dual_corpus_manager()

        if is_public:
            # Add to PUBLIC corpus (admin only)
            logger.info(f"Adding {len(documents)} chunks to PUBLIC corpus")
            chunk_ids = await corpus_manager.add_to_public(
                documents=documents,
                embeddings=embeddings
            )
            corpus_type = "PUBLIC"
        else:
            # Add to PRIVATE corpus (user upload)
            logger.info(f"Adding {len(documents)} chunks to PRIVATE corpus (org={org_id})")
            chunk_ids = await corpus_manager.add_to_private(
                documents=documents,
                embeddings=embeddings,
                org_id=org_id,
                user_id=user_id
            )
            corpus_type = "PRIVATE"

        logger.info(f"✓ Document {document_id} processed successfully")
        logger.info(f"  - Corpus: {corpus_type}")
        logger.info(f"  - Organization: {org_id}")
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
    is_public: bool = False,
    current_user: User = Depends(get_current_user),
):
    """
    Upload and process a legal document to PRIVATE corpus.

    **Authentication Required:** Bearer token in Authorization header

    Args:
        file: PDF, DOCX, or TXT file
        document_type: Type of document (judgment, statute, contract)
        is_public: If True, add to public corpus (requires admin privileges)

    **Corpus Routing:**
    - is_public=False (default): Document goes to PRIVATE corpus (org-specific)
    - is_public=True: Document goes to PUBLIC corpus (requires admin, shared across all users)

    **Returns:**
    - document_id: Unique identifier
    - status: Processing status
    - corpus: Which corpus the document was added to
    """
    try:
        # Check admin permission for public uploads
        if is_public and not current_user.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Only admins can upload to public corpus"
            )

        # Validate file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type {file_ext} not supported. Allowed: {settings.ALLOWED_EXTENSIONS}"
            )

        # Generate document ID
        document_id = str(uuid.uuid4())

        logger.info(
            f"Upload initiated: {file.filename} by user={current_user.user_id}, "
            f"org={current_user.org_id}, is_public={is_public}"
        )
        
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
        
        # Process in background with user context
        background_tasks.add_task(
            process_uploaded_document,
            str(file_path),
            document_id,
            document_type,
            current_user.user_id,
            current_user.org_id,
            is_public,
        )

        corpus_type = "PUBLIC" if is_public else "PRIVATE"
        message = (
            f"Document uploaded to {corpus_type} corpus. "
            f"Processing in background."
        )

        return UploadResponse(
            document_id=document_id,
            filename=file.filename,
            file_size=file_size,
            status="processing",
            message=message
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
    is_public: bool = False,
    current_user: User = Depends(get_current_user),
):
    """
    Upload multiple documents at once.

    **Authentication Required:** Bearer token in Authorization header

    All documents will be uploaded to the same corpus (public or private).
    """
    results = []

    for file in files:
        try:
            result = await upload_document(
                background_tasks=background_tasks,
                file=file,
                document_type=document_type,
                is_public=is_public,
                current_user=current_user,
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
        "results": results,
        "corpus": "PUBLIC" if is_public else "PRIVATE",
        "org_id": current_user.org_id
    }