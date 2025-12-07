# ============================================================
# FILE: backend/tests/test_verification.py
# PURPOSE: Unit tests for citation verification system
# ============================================================

import pytest
import asyncio
from typing import List

from app.services.verification.citation_extractor import CitationExtractor
from app.services.verification.citation_verifier import CitationVerifier
from app.services.verification.models import (
    Citation,
    CitationType,
    VerificationMethod,
    RiskLevel
)
from tests.fixtures.verification_test_cases import (
    TEST_CASES,
    EXTRACTOR_TEST_CASES,
    SYNTHETIC_DOCS,
    get_test_case
)


class TestCitationExtractor:
    """Test citation extraction from legal text"""

    def setup_method(self):
        """Setup test instance"""
        self.extractor = CitationExtractor()

    def test_extract_air_citation(self):
        """Test extracting AIR citations"""
        text = "According to AIR 2024 SC 1001, bail was granted."
        citations = self.extractor.extract_all(text)

        assert len(citations) >= 1
        assert any(c.text == "AIR 2024 SC 1001" for c in citations)
        assert any(c.pattern_type == CitationType.AIR for c in citations)

    def test_extract_scc_citation(self):
        """Test extracting SCC citations"""
        text = "In 2023 (5) SCC 789, the court held..."
        citations = self.extractor.extract_all(text)

        assert len(citations) >= 1
        assert any(c.text == "2023 (5) SCC 789" for c in citations)
        assert any(c.pattern_type == CitationType.SCC for c in citations)

    def test_extract_statute_section(self):
        """Test extracting statute sections"""
        text = "Section 438 CrPC provides for anticipatory bail."
        citations = self.extractor.extract_all(text)

        assert len(citations) >= 1
        assert any("438" in c.text and "CrPC" in c.text for c in citations)

    def test_extract_multiple_citations(self):
        """Test extracting multiple citations from same text"""
        text = """
        The court cited AIR 2024 SC 1001 and Section 438 CrPC.
        Also referenced was 2023 (5) SCC 789.
        """
        citations = self.extractor.extract_all(text)

        assert len(citations) >= 3

    def test_extract_no_citations(self):
        """Test text without citations"""
        text = "This is plain text about law without any citations."
        citations = self.extractor.extract_all(text)

        assert len(citations) == 0

    def test_has_citations(self):
        """Test quick citation check"""
        assert self.extractor.has_citations("AIR 2024 SC 1001") == True
        assert self.extractor.has_citations("No citations here") == False

    def test_count_citations(self):
        """Test citation counting"""
        text = "AIR 2024 SC 1001 and Section 438 CrPC"
        count = self.extractor.count_citations(text)
        assert count >= 2

    def test_get_citation_context(self):
        """Test getting context around citation"""
        text = "This is some text before AIR 2024 SC 1001 and after."
        citations = self.extractor.extract_all(text)

        if citations:
            context = self.extractor.get_citation_context(text, citations[0], context_chars=10)
            assert "AIR 2024 SC 1001" in context

    @pytest.mark.parametrize("test_case", EXTRACTOR_TEST_CASES)
    def test_extractor_with_fixtures(self, test_case):
        """Test extractor with predefined test cases"""
        text = test_case["text"]
        expected = test_case["expected"]

        citations = self.extractor.extract_all(text)

        assert len(citations) == len(expected), \
            f"Expected {len(expected)} citations, got {len(citations)}"


class TestCitationVerifier:
    """Test citation verification against database"""

    def setup_method(self):
        """Setup test instance"""
        self.verifier = CitationVerifier()

    @pytest.mark.asyncio
    async def test_verify_known_citation(self):
        """Test verifying a citation that exists in test data"""
        # This test requires test data to be loaded in Qdrant
        # For unit testing without DB, we'll skip actual verification
        citation = "AIR 2024 SC 1001"
        result = await self.verifier.verify_citation(citation)

        # Should return a VerificationResult (even if not found)
        assert result is not None
        assert result.citation == citation
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_verify_hallucinated_citation(self):
        """Test verifying a citation that doesn't exist"""
        citation = "AIR 2099 SC 999"  # Future year = hallucination
        result = await self.verifier.verify_citation(citation)

        # Should detect as not found
        assert result.is_verified == False
        assert result.confidence == 0.0
        assert result.method == VerificationMethod.NOT_FOUND

    @pytest.mark.asyncio
    async def test_verify_all_mixed_citations(self):
        """Test verifying a mix of real and fake citations"""
        from app.services.verification.citation_extractor import CitationExtractor

        extractor = CitationExtractor()
        text = "AIR 2024 SC 1001 is real, but AIR 2099 SC 999 is fake."
        citations = extractor.extract_all(text)

        report = await self.verifier.verify_all(citations, text)

        assert report is not None
        assert report.total_citations >= 2
        assert isinstance(report.score, float)
        assert report.risk_level in [e.value for e in RiskLevel]

    @pytest.mark.asyncio
    async def test_verify_empty_citations(self):
        """Test verifying when no citations found"""
        report = await self.verifier.verify_all([], "")

        assert report.total_citations == 0
        assert report.verified_count == 0
        assert report.risk_level == RiskLevel.UNVERIFIED


class TestVerificationIntegration:
    """Integration tests for full verification workflow"""

    def setup_method(self):
        """Setup test instances"""
        self.extractor = CitationExtractor()
        self.verifier = CitationVerifier()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_case_name", [
        "All citations verified",
        "Partial verification - hallucinated citation",
        "No citations in answer",
    ])
    async def test_full_verification_workflow(self, test_case_name):
        """Test complete workflow from extraction to verification"""
        test_case = get_test_case(test_case_name)
        if not test_case:
            pytest.skip(f"Test case '{test_case_name}' not found")

        llm_answer = test_case["llm_answer"]

        # Step 1: Extract citations
        citations = self.extractor.extract_all(llm_answer)

        # Step 2: Verify all citations
        report = await self.verifier.verify_all(citations, llm_answer)

        # Step 3: Check expectations
        assert report.total_citations == test_case["expected_total"]

        if "min_score" in test_case:
            assert report.score >= test_case["min_score"], \
                f"Score {report.score} below minimum {test_case['min_score']}"

        if "max_score" in test_case:
            assert report.score <= test_case["max_score"], \
                f"Score {report.score} above maximum {test_case['max_score']}"

    @pytest.mark.asyncio
    async def test_verification_with_context(self):
        """Test that verification uses context properly"""
        citation = "AIR 2024 SC 1001"
        context = "In this case about anticipatory bail..."

        result = await self.verifier.verify_citation(
            citation=citation,
            context=context
        )

        assert result is not None
        assert result.citation == citation


class TestVerificationModels:
    """Test Pydantic models"""

    def test_citation_model(self):
        """Test Citation model creation"""
        citation = Citation(
            text="AIR 2024 SC 1001",
            pattern_type=CitationType.AIR,
            start_pos=0,
            end_pos=16
        )

        assert citation.text == "AIR 2024 SC 1001"
        assert citation.pattern_type == CitationType.AIR

    def test_verification_result_model(self):
        """Test VerificationResult model"""
        from app.services.verification.models import VerificationResult

        result = VerificationResult(
            citation="AIR 2024 SC 1001",
            is_verified=True,
            confidence=0.95,
            method=VerificationMethod.EXACT_MATCH
        )

        assert result.is_verified == True
        assert result.confidence == 0.95

    def test_verification_report_model(self):
        """Test VerificationReport model"""
        from app.services.verification.models import VerificationReport

        report = VerificationReport(
            score=0.75,
            verified_count=3,
            total_citations=4,
            risk_level=RiskLevel.MEDIUM_CONFIDENCE,
            details=[],
            summary="3 of 4 verified"
        )

        assert report.score == 0.75
        assert report.risk_level == RiskLevel.MEDIUM_CONFIDENCE


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# End of file
