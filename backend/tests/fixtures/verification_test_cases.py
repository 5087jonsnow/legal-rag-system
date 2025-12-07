# ============================================================
# FILE: backend/tests/fixtures/verification_test_cases.py
# PURPOSE: Synthetic test data for citation verification
# ============================================================

"""
Synthetic test fixtures for citation verification.
Works without needing a real legal corpus in the database.
"""

from typing import List, Dict, Any


# Synthetic legal documents with known citations
SYNTHETIC_DOCS = [
    {
        "id": "doc_001",
        "citation": "AIR 2024 SC 1001",
        "text": """
        In the matter of anticipatory bail under Section 438 CrPC, the Supreme Court held:

        1. Bail granted subject to cooperation with investigation
        2. Applicant must surrender passport
        3. Regular reporting to local police station required

        The court emphasized that personal liberty under Article 21 is paramount but must be balanced
        with the need for effective investigation. Citing precedents from Arnesh Kumar v. State of Bihar
        and Siddharam Satlingappa Mhetre v. State of Maharashtra, the bench observed that arrest should
        not be routine in bailable offenses.
        """,
        "metadata": {
            "court": "Supreme Court",
            "year": 2024,
            "case_number": "1001",
            "citation_air": "AIR 2024 SC 1001",
            "statute_refs": ["Section 438 CrPC", "Article 21"],
            "bench_size": 2,
            "petitioner": "Ramesh Kumar",
            "respondent": "State of UP"
        }
    },
    {
        "id": "doc_002",
        "citation": "2023 (5) SCC 789",
        "text": """
        Contract Dispute: Interpretation of Force Majeure Clause

        The Supreme Court, in this landmark judgment on contract law, clarified the scope of force majeure
        clauses under the Indian Contract Act, 1872. The court held:

        1. COVID-19 pandemic qualifies as force majeure event
        2. Party claiming relief must prove direct causation
        3. Mere economic hardship is insufficient

        Section 56 of the Contract Act deals with agreements to do impossible acts. The court distinguished
        this case from Energy Watchdog v. CERC by noting that contractual impossibility must be objective,
        not subjective difficulty.
        """,
        "metadata": {
            "court": "Supreme Court",
            "year": 2023,
            "citation_scc": "2023 (5) SCC 789",
            "statute_refs": ["Section 56 Indian Contract Act"],
            "practice_area": "commercial",
            "bench_size": 3
        }
    },
    {
        "id": "doc_003",
        "citation": "AIR 2022 Del 456",
        "text": """
        Quashing of FIR under Section 482 CrPC - Delhi High Court

        The Delhi High Court quashed the FIR filed under Section 420 IPC observing that:

        1. Civil disputes should not be criminalized
        2. Allegations must disclose prima facie offense
        3. Continuation of proceedings would be abuse of process

        Following the principles laid down in State of Haryana v. Bhajan Lal, the court noted that
        inherent powers under Section 482 CrPC must be exercised sparingly to prevent miscarriage of justice.
        """,
        "metadata": {
            "court": "Delhi High Court",
            "year": 2022,
            "citation_air": "AIR 2022 Del 456",
            "statute_refs": ["Section 482 CrPC", "Section 420 IPC"],
            "practice_area": "criminal"
        }
    },
    {
        "id": "doc_004",
        "citation": "Section 438 CrPC",
        "text": """
        Criminal Procedure Code, 1973

        Section 438 - Direction for grant of bail to person apprehending arrest

        (1) Where any person has reason to believe that he may be arrested on accusation of having
        committed a non-bailable offence, he may apply to the High Court or the Court of Session
        for a direction under this section that in the event of such arrest, he shall be released on bail.

        (2) The High Court or the Court of Session may, if it thinks fit, direct that in the event of
        such arrest, the applicant shall be released on bail.

        This provision is often invoked in white-collar crimes, cases under PMLA, and other economic offenses
        where the accused apprehends arrest.
        """,
        "metadata": {
            "type": "statute",
            "act": "CrPC",
            "section": "438",
            "title": "Anticipatory Bail",
            "year_enacted": 1973
        }
    },
    {
        "id": "doc_005",
        "citation": "Article 21",
        "text": """
        Constitution of India

        Article 21 - Protection of Life and Personal Liberty

        No person shall be deprived of his life or personal liberty except according to procedure
        established by law.

        This fundamental right has been expansively interpreted by Indian courts to include:
        - Right to privacy (Puttaswamy judgment)
        - Right to speedy trial
        - Right to live with dignity
        - Right to clean environment
        - Right to health and medical treatment

        Article 21 is the cornerstone of personal freedoms and has been cited in thousands of judgments
        across all areas of law including criminal, civil, constitutional, and administrative law.
        """,
        "metadata": {
            "type": "constitutional_provision",
            "article": "21",
            "part": "III",
            "title": "Fundamental Rights"
        }
    }
]


# Test cases with expected verification results
TEST_CASES = [
    {
        "name": "All citations verified",
        "query": "What are the bail conditions in AIR 2024 SC 1001?",
        "llm_answer": """
        According to AIR 2024 SC 1001, the Supreme Court granted anticipatory bail under Section 438 CrPC
        subject to the following conditions:
        1. Cooperation with investigation
        2. Surrender of passport
        3. Regular police reporting

        The court emphasized Article 21 protections for personal liberty.
        """,
        "expected_citations": ["AIR 2024 SC 1001", "Section 438 CrPC", "Article 21"],
        "expected_verified": 3,
        "expected_total": 3,
        "expected_risk": "HIGH_CONFIDENCE",
        "min_score": 0.9
    },
    {
        "name": "Partial verification - hallucinated citation",
        "query": "What are recent Supreme Court judgments on bail?",
        "llm_answer": """
        In AIR 2024 SC 1001, the court granted bail citing Section 438 CrPC. However, a contrary view
        was taken in AIR 2099 SC 999 where bail was denied despite similar circumstances.
        """,
        "expected_citations": ["AIR 2024 SC 1001", "Section 438 CrPC", "AIR 2099 SC 999"],
        "expected_verified": 2,  # First two verified
        "expected_total": 3,
        "expected_risk": "MEDIUM_CONFIDENCE",
        "forbidden_verified": ["AIR 2099 SC 999"],  # This should NOT be verified (hallucination)
        "min_score": 0.6,
        "max_score": 0.8
    },
    {
        "name": "Contract law with SCC citation",
        "query": "How do courts interpret force majeure clauses?",
        "llm_answer": """
        In 2023 (5) SCC 789, the Supreme Court held that COVID-19 qualifies as a force majeure event
        under Section 56 Indian Contract Act. The party must prove direct causation.
        """,
        "expected_citations": ["2023 (5) SCC 789", "Section 56 Indian Contract Act"],
        "expected_verified": 2,
        "expected_total": 2,
        "expected_risk": "HIGH_CONFIDENCE",
        "min_score": 0.9
    },
    {
        "name": "High Court citation",
        "query": "When can FIR be quashed?",
        "llm_answer": """
        The Delhi High Court in AIR 2022 Del 456 quashed the FIR under Section 482 CrPC observing
        that civil disputes should not be criminalized. Section 420 IPC allegations did not disclose
        prima facie offense.
        """,
        "expected_citations": ["AIR 2022 Del 456", "Section 482 CrPC", "Section 420 IPC"],
        "expected_verified": 3,
        "expected_total": 3,
        "expected_risk": "HIGH_CONFIDENCE",
        "min_score": 0.85
    },
    {
        "name": "Multiple hallucinated citations",
        "query": "What are the latest judgments?",
        "llm_answer": """
        Recent judgments include AIR 2099 SC 999, AIR 2098 SC 888, and AIR 2097 SC 777.
        These cases establish new precedents on bail jurisprudence.
        """,
        "expected_citations": ["AIR 2099 SC 999", "AIR 2098 SC 888", "AIR 2097 SC 777"],
        "expected_verified": 0,  # All hallucinated
        "expected_total": 3,
        "expected_risk": "LOW_CONFIDENCE",
        "forbidden_verified": ["AIR 2099 SC 999", "AIR 2098 SC 888", "AIR 2097 SC 777"],
        "max_score": 0.2
    },
    {
        "name": "No citations in answer",
        "query": "What is bail?",
        "llm_answer": """
        Bail is a legal mechanism that allows an accused person to be released from custody while
        awaiting trial. It ensures the accused's presence during proceedings while respecting their
        right to liberty.
        """,
        "expected_citations": [],
        "expected_verified": 0,
        "expected_total": 0,
        "expected_risk": "UNVERIFIED",
        "expected_score": 0.0
    },
    {
        "name": "Statute-only references",
        "query": "What is the provision for anticipatory bail?",
        "llm_answer": """
        Section 438 CrPC provides for anticipatory bail. Article 21 of the Constitution protects
        personal liberty. These provisions work together to ensure fair criminal procedure.
        """,
        "expected_citations": ["Section 438 CrPC", "Article 21"],
        "expected_verified": 2,
        "expected_total": 2,
        "expected_risk": "HIGH_CONFIDENCE",
        "min_score": 0.9
    }
]


# Citation regex patterns for testing
CITATION_PATTERNS = {
    "air": r'AIR\s+\d{4}\s+[A-Z][a-z]*\s+\d+',  # AIR 2024 SC 1001, AIR 2022 Del 456
    "scc": r'\d{4}\s+\(\d+\)\s+SCC\s+\d+',  # 2023 (5) SCC 789
    "statute_section": r'Section\s+\d+[A-Z]?\s+[A-Z][a-zA-Z\s]+',  # Section 438 CrPC
    "article": r'Article\s+\d+[A-Z]?',  # Article 21
    "ipc_section": r'Section\s+\d+[A-Z]?\s+IPC',  # Section 420 IPC
}


# Helper function to get synthetic docs by citation
def get_doc_by_citation(citation: str) -> Dict[str, Any]:
    """Get synthetic document by citation string"""
    citation_normalized = citation.strip().upper()

    for doc in SYNTHETIC_DOCS:
        # Check all citation fields in metadata
        doc_citations = [
            doc.get("citation", "").upper(),
            doc.get("metadata", {}).get("citation_air", "").upper(),
            doc.get("metadata", {}).get("citation_scc", "").upper(),
        ]

        if citation_normalized in " ".join(doc_citations):
            return doc

    return None


# Helper function to get test case by name
def get_test_case(name: str) -> Dict[str, Any]:
    """Get test case by name"""
    for tc in TEST_CASES:
        if tc["name"] == name:
            return tc
    return None


# Expected extraction results for testing citation extractor
EXTRACTOR_TEST_CASES = [
    {
        "text": "AIR 2024 SC 1001 states that...",
        "expected": [
            {"text": "AIR 2024 SC 1001", "pattern_type": "air", "start_pos": 0}
        ]
    },
    {
        "text": "According to 2023 (5) SCC 789 and Section 438 CrPC...",
        "expected": [
            {"text": "2023 (5) SCC 789", "pattern_type": "scc"},
            {"text": "Section 438 CrPC", "pattern_type": "statute"}
        ]
    },
    {
        "text": "No citations here, just plain text about law.",
        "expected": []
    },
    {
        "text": "Multiple citations: AIR 2024 SC 1001, AIR 2022 Del 456, and Article 21",
        "expected": [
            {"text": "AIR 2024 SC 1001", "pattern_type": "air"},
            {"text": "AIR 2022 Del 456", "pattern_type": "air"},
            {"text": "Article 21", "pattern_type": "article"}
        ]
    }
]


# End of file
