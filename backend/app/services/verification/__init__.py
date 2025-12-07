# ============================================================
# FILE: backend/app/services/verification/__init__.py
# PURPOSE: Verification service package initialization
# ============================================================

from .models import (
    Citation,
    VerificationResult,
    VerificationReport,
    RiskLevel,
    VerificationMethod
)
from .citation_extractor import CitationExtractor
from .citation_verifier import CitationVerifier

__all__ = [
    "Citation",
    "VerificationResult",
    "VerificationReport",
    "RiskLevel",
    "VerificationMethod",
    "CitationExtractor",
    "CitationVerifier",
]

# End of file
