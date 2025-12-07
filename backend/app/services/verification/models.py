# ============================================================
# FILE: backend/app/services/verification/models.py
# PURPOSE: Pydantic models for citation verification
# ============================================================

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class CitationType(str, Enum):
    """Types of Indian legal citations"""
    AIR = "air"  # All India Reporter (e.g., AIR 2024 SC 1001)
    SCC = "scc"  # Supreme Court Cases (e.g., 2024 (1) SCC 1001)
    STATUTE = "statute"  # Statutory references (e.g., Section 438 CrPC)
    ILR = "ilr"  # Indian Law Reports
    SCR = "scr"  # Supreme Court Reports
    HC = "hc"  # High Court citations
    CUSTOM = "custom"  # Other citation formats


class VerificationMethod(str, Enum):
    """How the citation was verified"""
    EXACT_MATCH = "exact_match"  # Found exact citation in metadata
    FUZZY_MATCH = "fuzzy_match"  # Found similar citation (e.g., AIR vs SCC)
    SEMANTIC_MATCH = "semantic_match"  # Found by content similarity
    STATUTE_MATCH = "statute_match"  # Verified statute reference
    NOT_FOUND = "not_found"  # Citation not found in database


class RiskLevel(str, Enum):
    """Risk level of the entire answer"""
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"  # >=80% verified
    MEDIUM_CONFIDENCE = "MEDIUM_CONFIDENCE"  # 50-79% verified
    LOW_CONFIDENCE = "LOW_CONFIDENCE"  # <50% verified
    UNVERIFIED = "UNVERIFIED"  # No citations found


class Citation(BaseModel):
    """Extracted citation from LLM answer"""
    text: str = Field(..., description="Raw citation text")
    pattern_type: CitationType = Field(..., description="Type of citation")
    start_pos: int = Field(..., description="Character position in answer")
    end_pos: int = Field(..., description="End character position")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "AIR 2024 SC 1001",
                "pattern_type": "air",
                "start_pos": 45,
                "end_pos": 61
            }
        }


class VerificationResult(BaseModel):
    """Verification result for a single citation"""
    citation: str = Field(..., description="The citation being verified")
    is_verified: bool = Field(..., description="Whether citation was found")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    method: VerificationMethod = Field(..., description="How it was verified")
    source_doc_id: Optional[str] = Field(None, description="Qdrant document ID if found")
    snippet: Optional[str] = Field(None, description="Text snippet from source")
    warning: Optional[str] = Field(None, description="Warning message if not verified")
    metadata: Optional[dict] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "citation": "AIR 2024 SC 1001",
                "is_verified": True,
                "confidence": 0.95,
                "method": "exact_match",
                "source_doc_id": "doc_12345",
                "snippet": "In the matter of anticipatory bail...",
                "warning": None,
                "metadata": {"court": "Supreme Court", "year": 2024}
            }
        }


class VerificationReport(BaseModel):
    """Complete verification report for an answer"""
    score: float = Field(..., ge=0.0, le=1.0, description="Overall verification score")
    verified_count: int = Field(..., ge=0, description="Number of verified citations")
    total_citations: int = Field(..., ge=0, description="Total citations found")
    risk_level: RiskLevel = Field(..., description="Risk assessment")
    details: List[VerificationResult] = Field(..., description="Per-citation results")
    summary: str = Field(..., description="Human-readable summary")

    class Config:
        json_schema_extra = {
            "example": {
                "score": 0.67,
                "verified_count": 2,
                "total_citations": 3,
                "risk_level": "MEDIUM_CONFIDENCE",
                "details": [
                    {
                        "citation": "AIR 2024 SC 1001",
                        "is_verified": True,
                        "confidence": 0.95,
                        "method": "exact_match"
                    }
                ],
                "summary": "2 of 3 citations verified. Medium confidence."
            }
        }


# End of file
