# ============================================================
# FILE: backend/app/services/verification/citation_verifier.py
# PURPOSE: Verify citations against Qdrant database
# ============================================================

import re
from typing import List, Optional
import logging
from difflib import SequenceMatcher

from qdrant_client import QdrantClient
from app.core.config import settings

from .models import (
    Citation,
    VerificationResult,
    VerificationReport,
    VerificationMethod,
    RiskLevel
)
from .citation_extractor import CitationExtractor

logger = logging.getLogger(__name__)


class CitationVerifier:
    """
    Verify legal citations against documents in Qdrant database.

    Verification methods (in order of preference):
    1. Exact match in metadata (confidence: 1.0)
    2. Fuzzy match in metadata (confidence: 0.8)
    3. Semantic search in content (confidence: 0.6)
    4. Not found (confidence: 0.0)
    """

    def __init__(self):
        """Initialize the citation verifier with Qdrant client"""
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT
        )
        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.extractor = CitationExtractor()

        logger.info(f"CitationVerifier initialized for collection: {self.collection_name}")

    async def verify_citation(
        self,
        citation: str,
        context: str = "",
        collection_name: Optional[str] = None
    ) -> VerificationResult:
        """
        Verify a single citation against the database.

        Args:
            citation: Citation string to verify (e.g., "AIR 2024 SC 1001")
            context: Surrounding context from the answer (helps with semantic search)
            collection_name: Optional collection name (defaults to primary collection)

        Returns:
            VerificationResult with verification details
        """
        collection = collection_name or self.collection_name

        try:
            # 1. Try exact match in metadata
            exact_result = await self._verify_exact_match(citation, collection)
            if exact_result:
                return exact_result

            # 2. Try fuzzy match in metadata
            fuzzy_result = await self._verify_fuzzy_match(citation, collection)
            if fuzzy_result:
                return fuzzy_result

            # 3. Try semantic search (if context provided)
            if context:
                semantic_result = await self._verify_semantic_match(
                    citation, context, collection
                )
                if semantic_result:
                    return semantic_result

            # 4. Not found
            return VerificationResult(
                citation=citation,
                is_verified=False,
                confidence=0.0,
                method=VerificationMethod.NOT_FOUND,
                warning="Citation not found in database - possible hallucination",
                metadata={}
            )

        except Exception as e:
            logger.error(f"Error verifying citation '{citation}': {e}", exc_info=True)
            return VerificationResult(
                citation=citation,
                is_verified=False,
                confidence=0.0,
                method=VerificationMethod.NOT_FOUND,
                warning=f"Verification failed: {str(e)}",
                metadata={}
            )

    async def verify_all(
        self,
        citations: List[Citation],
        full_text: str = "",
        collection_name: Optional[str] = None
    ) -> VerificationReport:
        """
        Verify all citations and generate a verification report.

        Args:
            citations: List of Citation objects
            full_text: Full answer text for context
            collection_name: Optional collection name

        Returns:
            VerificationReport with overall verification score
        """
        if not citations:
            return VerificationReport(
                score=0.0,
                verified_count=0,
                total_citations=0,
                risk_level=RiskLevel.UNVERIFIED,
                details=[],
                summary="No citations found in answer"
            )

        results = []
        verified_count = 0
        total_confidence = 0.0

        for citation in citations:
            # Get context around citation
            context = self.extractor.get_citation_context(
                full_text, citation, context_chars=150
            )

            # Verify citation
            result = await self.verify_citation(
                citation=citation.text,
                context=context,
                collection_name=collection_name
            )

            results.append(result)

            if result.is_verified:
                verified_count += 1

            total_confidence += result.confidence

        # Calculate overall score
        total_citations = len(citations)
        score = total_confidence / total_citations if total_citations > 0 else 0.0

        # Determine risk level
        verification_ratio = verified_count / total_citations if total_citations > 0 else 0.0

        if verification_ratio >= 0.8:
            risk_level = RiskLevel.HIGH_CONFIDENCE
        elif verification_ratio >= 0.5:
            risk_level = RiskLevel.MEDIUM_CONFIDENCE
        else:
            risk_level = RiskLevel.LOW_CONFIDENCE

        # Generate summary
        summary = (
            f"{verified_count} of {total_citations} citations verified. "
            f"{risk_level.value.replace('_', ' ').title()}."
        )

        return VerificationReport(
            score=round(score, 2),
            verified_count=verified_count,
            total_citations=total_citations,
            risk_level=risk_level,
            details=results,
            summary=summary
        )

    async def _verify_exact_match(
        self,
        citation: str,
        collection: str
    ) -> Optional[VerificationResult]:
        """
        Verify by exact match in metadata fields.

        Checks metadata fields like:
        - citation_air, citation_scc, citation_ilr
        - case_number, year, court
        """
        try:
            # Normalize citation
            citation_normalized = citation.strip().upper()

            # Scroll through documents to check metadata
            # (In production, use metadata filtering if Qdrant supports it)
            scroll_result = self.client.scroll(
                collection_name=collection,
                limit=100,  # Check first 100 docs (expand for production)
                with_payload=True,
                with_vectors=False
            )

            points = scroll_result[0]

            for point in points:
                payload = point.payload

                # Check various citation metadata fields
                citation_fields = [
                    payload.get("citation", ""),
                    payload.get("citation_air", ""),
                    payload.get("citation_scc", ""),
                    payload.get("citation_ilr", ""),
                ]

                for field_value in citation_fields:
                    if field_value and field_value.strip().upper() == citation_normalized:
                        return VerificationResult(
                            citation=citation,
                            is_verified=True,
                            confidence=1.0,
                            method=VerificationMethod.EXACT_MATCH,
                            source_doc_id=str(point.id),
                            snippet=payload.get("text", "")[:200] + "...",
                            metadata={
                                "court": payload.get("court"),
                                "year": payload.get("year"),
                                "case_number": payload.get("case_number"),
                            }
                        )

            return None

        except Exception as e:
            logger.warning(f"Exact match verification failed: {e}")
            return None

    async def _verify_fuzzy_match(
        self,
        citation: str,
        collection: str,
        similarity_threshold: float = 0.85
    ) -> Optional[VerificationResult]:
        """
        Verify by fuzzy string matching.

        Useful for:
        - Different citation formats (AIR vs SCC for same case)
        - Minor typos
        - Variations in spacing/punctuation
        """
        try:
            citation_normalized = citation.strip().upper()

            scroll_result = self.client.scroll(
                collection_name=collection,
                limit=100,
                with_payload=True,
                with_vectors=False
            )

            points = scroll_result[0]
            best_match = None
            best_similarity = 0.0

            for point in points:
                payload = point.payload

                citation_fields = [
                    payload.get("citation", ""),
                    payload.get("citation_air", ""),
                    payload.get("citation_scc", ""),
                ]

                for field_value in citation_fields:
                    if not field_value:
                        continue

                    # Calculate string similarity
                    similarity = SequenceMatcher(
                        None,
                        citation_normalized,
                        field_value.strip().upper()
                    ).ratio()

                    if similarity > best_similarity and similarity >= similarity_threshold:
                        best_similarity = similarity
                        best_match = {
                            "point": point,
                            "matched_field": field_value,
                            "similarity": similarity
                        }

            if best_match:
                point = best_match["point"]
                payload = point.payload

                return VerificationResult(
                    citation=citation,
                    is_verified=True,
                    confidence=round(best_similarity * 0.8, 2),  # Scale down slightly
                    method=VerificationMethod.FUZZY_MATCH,
                    source_doc_id=str(point.id),
                    snippet=payload.get("text", "")[:200] + "...",
                    metadata={
                        "matched_citation": best_match["matched_field"],
                        "similarity": round(best_similarity, 2),
                        "court": payload.get("court"),
                        "year": payload.get("year"),
                    }
                )

            return None

        except Exception as e:
            logger.warning(f"Fuzzy match verification failed: {e}")
            return None

    async def _verify_semantic_match(
        self,
        citation: str,
        context: str,
        collection: str,
        similarity_threshold: float = 0.7
    ) -> Optional[VerificationResult]:
        """
        Verify by semantic search of citation + context.

        Uses embedding similarity to find relevant documents
        that might contain the cited case.
        """
        # Note: This requires embedding model, which adds complexity.
        # For MVP, we'll skip semantic matching and rely on exact/fuzzy.
        # In production, integrate with Legal-BERT embeddings.

        logger.debug(f"Semantic matching skipped for MVP: {citation}")
        return None


# Singleton instance
_citation_verifier = None

def get_citation_verifier() -> CitationVerifier:
    """Get or create the citation verifier singleton"""
    global _citation_verifier
    if _citation_verifier is None:
        _citation_verifier = CitationVerifier()
    return _citation_verifier


# End of file
