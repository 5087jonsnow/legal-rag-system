"""
LlamaIndex RAG Service with Citation Verification
Production RAG using LlamaIndex framework + verification
"""

from typing import List, Optional, Dict, Any
import logging

from app.services.verification.citation_extractor import CitationExtractor
from app.services.verification.citation_verifier import CitationVerifier
from app.services.corpus.dual_corpus_manager import DualCorpusManager

logger = logging.getLogger(__name__)


class LlamaIndexRAG:
    """
    Production RAG using LlamaIndex
    
    Replaces custom RAG while keeping legal metadata extraction
    Uses existing Qdrant data and Legal-BERT embeddings
    """
    
    def __init__(self):
        self._initialized = False
        self.index = None
        self.query_engine = None

        # Citation verification components
        self.citation_extractor = CitationExtractor()
        self.citation_verifier = CitationVerifier()

        # Dual corpus manager
        self.corpus_manager = DualCorpusManager()
    
    def initialize(self):
        """Initialize LlamaIndex (called once on startup)"""
        if self._initialized:
            logger.info("LlamaIndex already initialized")
            return
        
        try:
            logger.info("🚀 Initializing LlamaIndex RAG...")
            
            # Import here to avoid startup issues
            from llama_index.core import VectorStoreIndex, StorageContext, Settings
            from llama_index.vector_stores.qdrant import QdrantVectorStore
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
            from llama_index.llms.groq import Groq
            from qdrant_client import QdrantClient
            from app.core.config import settings as app_settings
            
            # 1. Connect to existing Qdrant
            logger.info("   📦 Connecting to Qdrant...")
            client = QdrantClient(
                host=app_settings.QDRANT_HOST,
                port=app_settings.QDRANT_PORT
            )
            
            vector_store = QdrantVectorStore(
                client=client,
                collection_name="legal_documents"
            )
            
            # 2. Use existing Legal-BERT embeddings
            logger.info("   🧠 Loading Legal-BERT embeddings...")
            embed_model = HuggingFaceEmbedding(
                model_name="nlpaueb/legal-bert-base-uncased"
            )
            
            # 3. Set up Groq LLM
            logger.info("   🤖 Setting up Groq LLM...")
            llm = Groq(
                model="llama-3.3-70b-versatile",
                api_key=app_settings.GROQ_API_KEY,
                temperature=0.1
            )
            
            # 4. Configure LlamaIndex global settings
            Settings.llm = llm
            Settings.embed_model = embed_model
            Settings.chunk_size = 1000
            Settings.chunk_overlap = 200
            
            # 5. Create index from existing vectors
            logger.info("   🔍 Creating index from existing vectors...")
            storage_context = StorageContext.from_defaults(
                vector_store=vector_store
            )
            
            self.index = VectorStoreIndex.from_vector_store(
                vector_store,
                storage_context=storage_context
            )
            
            # 6. Create query engine
            logger.info("   ⚙️  Setting up query engine...")
            self.query_engine = self.index.as_query_engine(
                similarity_top_k=5,
                response_mode="compact",
                streaming=False
            )
            
            self._initialized = True
            logger.info("✅ LlamaIndex RAG initialized successfully!")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize LlamaIndex: {e}", exc_info=True)
            raise
    
    async def search_and_answer(
        self,
        query: str,
        top_k: int = 5,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        enable_verification: bool = True
    ) -> Dict[str, Any]:
        """
        Search using LlamaIndex and generate answer with citation verification

        Args:
            query: User's legal question
            top_k: Number of source documents to retrieve
            user_id: User ID (for dual corpus filtering)
            org_id: Organization ID (for dual corpus filtering)
            enable_verification: Whether to verify citations

        Returns:
            Dict with answer, sources, and verification report
        """
        # Ensure initialized
        if not self._initialized:
            self.initialize()

        try:
            logger.info(f"🔍 LlamaIndex query: '{query}' (top_k={top_k}, user={user_id}, org={org_id})")

            # Update similarity_top_k for this query
            self.query_engine.similarity_top_k = top_k

            # Query with LlamaIndex
            response = self.query_engine.query(query)
            answer_text = str(response)

            # Extract sources
            sources = []
            for node in response.source_nodes:
                sources.append({
                    'text': node.node.text,
                    'score': float(node.score),
                    'metadata': node.node.metadata,
                    'doc_id': node.node.id_
                })

            # CITATION VERIFICATION (NEW!)
            verification = None
            if enable_verification:
                try:
                    logger.info("🔍 Verifying citations in answer...")

                    # Extract citations from answer
                    citations = self.citation_extractor.extract_all(answer_text)

                    if citations:
                        # Verify all citations
                        verification_report = await self.citation_verifier.verify_all(
                            citations=citations,
                            full_text=answer_text
                        )

                        verification = verification_report.dict()

                        logger.info(
                            f"✅ Verification complete: {verification_report.verified_count}/"
                            f"{verification_report.total_citations} citations verified "
                            f"({verification_report.risk_level})"
                        )
                    else:
                        # No citations found
                        from app.services.verification.models import VerificationReport, RiskLevel
                        verification_report = VerificationReport(
                            score=0.0,
                            verified_count=0,
                            total_citations=0,
                            risk_level=RiskLevel.UNVERIFIED,
                            details=[],
                            summary="No citations found in answer"
                        )
                        verification = verification_report.dict()

                except Exception as e:
                    logger.error(f"⚠️ Verification failed: {e}", exc_info=True)
                    # Don't fail the request if verification fails
                    verification = {
                        "error": str(e),
                        "message": "Citation verification failed"
                    }

            result = {
                'answer': answer_text,
                'sources': sources,
                'source_count': len(sources),
                'query': query,
                'engine': 'llamaindex',
                'verification': verification  # NEW: Verification report
            }

            logger.info(f"✅ Found {len(sources)} sources, generated answer with verification")
            return result

        except Exception as e:
            logger.error(f"❌ Query failed: {e}", exc_info=True)
            raise
    
    async def search_only(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search without generating answer (retrieval only)
        
        Use when you only want source documents, not AI answer
        """
        if not self._initialized:
            self.initialize()
        
        try:
            logger.info(f"🔍 LlamaIndex retrieval: '{query}' (top_k={top_k})")
            
            # Use retriever directly
            retriever = self.index.as_retriever(similarity_top_k=top_k)
            nodes = retriever.retrieve(query)
            
            results = []
            for node in nodes:
                results.append({
                    'text': node.node.text,
                    'score': float(node.score),
                    'metadata': node.node.metadata,
                    'doc_id': node.node.id_
                })
            
            logger.info(f"✅ Retrieved {len(results)} documents")
            return results
            
        except Exception as e:
            logger.error(f"❌ Retrieval failed: {e}", exc_info=True)
            raise


# Singleton instance
_llamaindex_rag = None

def get_llamaindex_rag() -> LlamaIndexRAG:
    """Get or create the LlamaIndex RAG instance"""
    global _llamaindex_rag
    if _llamaindex_rag is None:
        _llamaindex_rag = LlamaIndexRAG()
    return _llamaindex_rag