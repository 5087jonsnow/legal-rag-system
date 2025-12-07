# ============================================================
# FILE: backend/app/services/verification/citation_extractor.py
# PURPOSE: Extract Indian legal citations from LLM answers using regex
# ============================================================

import re
from typing import List
import logging

from .models import Citation, CitationType

logger = logging.getLogger(__name__)


class CitationExtractor:
    """
    Extract Indian legal citations from text using regex patterns.

    Supports:
    - AIR (All India Reporter): AIR 2024 SC 1001
    - SCC (Supreme Court Cases): 2024 (1) SCC 1001
    - ILR (Indian Law Reports): ILR 2024 SC 1001
    - Statutes: Section 438 CrPC, Section 420 IPC
    - Constitutional: Article 21, Article 14(1)
    - High Courts: AIR 2022 Del 456, 2023 Bom HC 789
    """

    # Regex patterns for Indian legal citations
    PATTERNS = {
        # All India Reporter - Most common format
        # Examples: AIR 2024 SC 1001, AIR 2022 Del 456, AIR 2023 Bom 789
        CitationType.AIR: r'AIR\s+\d{4}\s+[A-Z][a-z]*\s+\d+',

        # Supreme Court Cases
        # Examples: 2024 (1) SCC 1001, 2023 (5) SCC 789
        CitationType.SCC: r'\d{4}\s+\(\d+\)\s+SCC\s+\d+',

        # Indian Law Reports
        # Examples: ILR 2024 SC 1001, ILR 2023 Del 456
        CitationType.ILR: r'ILR\s+\d{4}\s+[A-Z][a-z]*\s+\d+',

        # Supreme Court Reports
        # Examples: 2024 SCR 1001
        CitationType.SCR: r'\d{4}\s+SCR\s+\d+',

        # High Court patterns (more flexible)
        # Examples: 2023 Bom HC 456, 2024 Del HC 789
        CitationType.HC: r'\d{4}\s+[A-Z][a-z]+\s+HC\s+\d+',

        # Statutory sections - Criminal Procedure Code
        # Examples: Section 438 CrPC, Section 482 CrPC, Section 41A CrPC
        CitationType.STATUTE: r'Section\s+\d+[A-Z]?\s+(?:CrPC|Cr\.?\s*P\.?C\.?)',

        # Indian Penal Code sections
        # Examples: Section 420 IPC, Section 302 IPC
        'ipc': r'Section\s+\d+[A-Z]?\s+(?:IPC|I\.?\s*P\.?C\.?)',

        # Indian Evidence Act
        # Examples: Section 65B Evidence Act
        'evidence_act': r'Section\s+\d+[A-Z]?\s+(?:Evidence\s+Act|Indian\s+Evidence\s+Act)',

        # Indian Contract Act
        # Examples: Section 56 Indian Contract Act, Section 73 Contract Act
        'contract_act': r'Section\s+\d+[A-Z]?\s+(?:Indian\s+)?Contract\s+Act',

        # Constitutional Articles
        # Examples: Article 21, Article 14, Article 226(1)
        'article': r'Article\s+\d+[A-Z]?(?:\(\d+\))?',

        # Generic statute sections (catch-all)
        # Examples: Section 138 NI Act, Section 7 PMLA
        'generic_statute': r'Section\s+\d+[A-Z]?\s+[A-Z][A-Z\s]+(?:Act)?',
    }

    def __init__(self):
        """Initialize the citation extractor with compiled regex patterns"""
        # Compile all patterns for better performance
        self.compiled_patterns = {
            pattern_type: re.compile(pattern, re.IGNORECASE)
            for pattern_type, pattern in self.PATTERNS.items()
        }

        logger.info(f"CitationExtractor initialized with {len(self.compiled_patterns)} patterns")

    def extract_all(self, text: str) -> List[Citation]:
        """
        Extract all citations from text.

        Args:
            text: Text to extract citations from (typically LLM answer)

        Returns:
            List of Citation objects sorted by position
        """
        if not text:
            return []

        citations = []
        seen_citations = set()  # Avoid duplicates

        # Try each pattern
        for pattern_type, compiled_pattern in self.compiled_patterns.items():
            matches = compiled_pattern.finditer(text)

            for match in matches:
                citation_text = match.group(0).strip()
                start_pos = match.start()
                end_pos = match.end()

                # Normalize citation text for deduplication
                normalized = citation_text.lower().strip()

                # Skip if we've already found this citation
                if normalized in seen_citations:
                    continue

                seen_citations.add(normalized)

                # Map pattern type to CitationType enum
                citation_type = self._map_pattern_type(pattern_type)

                citation = Citation(
                    text=citation_text,
                    pattern_type=citation_type,
                    start_pos=start_pos,
                    end_pos=end_pos
                )

                citations.append(citation)

        # Sort by position in text
        citations.sort(key=lambda c: c.start_pos)

        logger.info(f"Extracted {len(citations)} citations from text (length: {len(text)})")

        return citations

    def extract_by_type(self, text: str, citation_type: CitationType) -> List[Citation]:
        """
        Extract only citations of a specific type.

        Args:
            text: Text to extract from
            citation_type: Type of citation to extract

        Returns:
            List of citations of the specified type
        """
        all_citations = self.extract_all(text)
        return [c for c in all_citations if c.pattern_type == citation_type]

    def has_citations(self, text: str) -> bool:
        """
        Quick check if text contains any citations.

        Args:
            text: Text to check

        Returns:
            True if any citations found
        """
        return len(self.extract_all(text)) > 0

    def count_citations(self, text: str) -> int:
        """
        Count total citations in text.

        Args:
            text: Text to count citations in

        Returns:
            Number of unique citations found
        """
        return len(self.extract_all(text))

    def _map_pattern_type(self, pattern_type) -> CitationType:
        """Map internal pattern type to CitationType enum"""
        # Direct enum types
        if isinstance(pattern_type, CitationType):
            return pattern_type

        # String pattern types (for custom patterns)
        mapping = {
            'ipc': CitationType.STATUTE,
            'evidence_act': CitationType.STATUTE,
            'contract_act': CitationType.STATUTE,
            'article': CitationType.STATUTE,  # Treat articles as statute for now
            'generic_statute': CitationType.STATUTE,
        }

        return mapping.get(pattern_type, CitationType.CUSTOM)

    def get_citation_context(self, text: str, citation: Citation,
                            context_chars: int = 100) -> str:
        """
        Get surrounding context for a citation.

        Args:
            text: Full text
            citation: Citation object
            context_chars: Characters before/after citation

        Returns:
            Context string with citation highlighted
        """
        start = max(0, citation.start_pos - context_chars)
        end = min(len(text), citation.end_pos + context_chars)

        context = text[start:end]

        # Add ellipsis if truncated
        if start > 0:
            context = "..." + context
        if end < len(text):
            context = context + "..."

        return context


# Singleton instance
_citation_extractor = None

def get_citation_extractor() -> CitationExtractor:
    """Get or create the citation extractor singleton"""
    global _citation_extractor
    if _citation_extractor is None:
        _citation_extractor = CitationExtractor()
    return _citation_extractor


# End of file
