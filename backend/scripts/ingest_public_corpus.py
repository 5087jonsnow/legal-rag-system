# ============================================================
# FILE: backend/scripts/ingest_public_corpus.py
# PURPOSE: Scrape and ingest public legal corpus (SC/HC judgments, statutes)
# ============================================================

"""
Public corpus ingestion pipeline.

Data sources (free & legal):
1. Indian Kanoon API - https://indiankanoon.org
2. Supreme Court website - https://main.sci.gov.in
3. Local statute files (IPC, CrPC, Evidence Act)

Target: 500 documents for MVP
- 200 Supreme Court judgments
- 100 High Court judgments
- 100 Statutes (section-level chunks)
- 100 Test synthetic documents
"""

import asyncio
import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
from pathlib import Path

from transformers import AutoTokenizer, AutoModel
import torch
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

import sys
sys.path.append(str(Path(__file__).parent.parent))

from app.core.config import settings
from app.services.corpus.dual_corpus_manager import DualCorpusManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PublicCorpusIngester:
    """Ingest public legal documents into Qdrant"""

    def __init__(self):
        self.corpus_manager = DualCorpusManager()
        self.embedding_model = None
        self.tokenizer = None

        logger.info("PublicCorpusIngester initialized")

    def _load_embedding_model(self):
        """Load Legal-BERT embedding model"""
        if self.embedding_model is None:
            logger.info("Loading Legal-BERT embedding model...")
            self.tokenizer = AutoTokenizer.from_pretrained(settings.EMBEDDING_MODEL_NAME)
            self.embedding_model = AutoModel.from_pretrained(settings.EMBEDDING_MODEL_NAME)
            logger.info("✅ Embedding model loaded")

    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using Legal-BERT"""
        self._load_embedding_model()

        embeddings = []

        for text in texts:
            # Tokenize
            inputs = self.tokenizer(
                text,
                max_length=512,
                truncation=True,
                padding=True,
                return_tensors="pt"
            )

            # Generate embedding
            with torch.no_grad():
                outputs = self.embedding_model(**inputs)
                # Use CLS token embedding
                embedding = outputs.last_hidden_state[:, 0, :].squeeze().numpy()

            embeddings.append(embedding.tolist())

        return embeddings

    async def ingest_synthetic_test_data(self) -> int:
        """
        Ingest synthetic test documents for verification testing.

        This allows testing citation verification without scraping real data.
        """
        logger.info("📦 Ingesting synthetic test data...")

        from tests.fixtures.verification_test_cases import SYNTHETIC_DOCS

        documents = []
        texts = []

        for doc in SYNTHETIC_DOCS:
            documents.append({
                "id": doc["id"],
                "text": doc["text"].strip(),
                "metadata": doc["metadata"]
            })
            texts.append(doc["text"].strip())

        # Generate embeddings
        logger.info(f"   Generating embeddings for {len(texts)} documents...")
        embeddings = self._generate_embeddings(texts)

        # Add to public corpus
        logger.info(f"   Adding to public corpus...")
        doc_ids = await self.corpus_manager.add_to_public(
            documents=documents,
            embeddings=embeddings
        )

        logger.info(f"✅ Ingested {len(doc_ids)} synthetic test documents")
        return len(doc_ids)

    async def ingest_statutes(self, statute_file: Path) -> int:
        """
        Ingest statute sections from JSON file.

        Args:
            statute_file: Path to JSON file with statute sections

        Returns:
            Number of sections ingested
        """
        logger.info(f"📜 Ingesting statutes from {statute_file}...")

        if not statute_file.exists():
            logger.warning(f"Statute file not found: {statute_file}")
            return 0

        with open(statute_file, "r", encoding="utf-8") as f:
            statutes = json.load(f)

        documents = []
        texts = []

        for statute in statutes:
            doc_id = f"statute_{statute['act']}_{statute['section']}"

            documents.append({
                "id": doc_id,
                "text": statute["text"],
                "metadata": {
                    "type": "statute",
                    "act": statute["act"],
                    "section": statute["section"],
                    "title": statute.get("title", ""),
                    "year_enacted": statute.get("year_enacted"),
                }
            })
            texts.append(statute["text"])

        # Generate embeddings
        logger.info(f"   Generating embeddings for {len(texts)} statute sections...")
        embeddings = self._generate_embeddings(texts)

        # Add to public corpus
        logger.info(f"   Adding to public corpus...")
        doc_ids = await self.corpus_manager.add_to_public(
            documents=documents,
            embeddings=embeddings
        )

        logger.info(f"✅ Ingested {len(doc_ids)} statute sections")
        return len(doc_ids)

    async def scrape_indian_kanoon(
        self,
        query: str,
        limit: int = 100,
        court: str = "Supreme Court"
    ) -> List[Dict[str, Any]]:
        """
        Scrape judgments from Indian Kanoon.

        NOTE: This is a placeholder. In production:
        1. Use Indian Kanoon API (if available)
        2. Or use web scraping with proper rate limiting
        3. Or manually download judgment PDFs

        Args:
            query: Search query (e.g., "anticipatory bail")
            limit: Number of judgments
            court: Court filter

        Returns:
            List of judgment documents
        """
        logger.warning(
            "⚠️  Indian Kanoon scraping not implemented. "
            "Use manual download or API integration."
        )

        # Placeholder: Return empty list
        # In production, implement actual scraping/API calls here
        return []

    async def ingest_from_directory(
        self,
        directory: Path,
        file_pattern: str = "*.txt"
    ) -> int:
        """
        Ingest legal documents from a directory.

        Useful for:
        - Manually downloaded judgments
        - Statute text files
        - OCR-processed PDFs

        Args:
            directory: Directory containing documents
            file_pattern: Glob pattern for files

        Returns:
            Number of documents ingested
        """
        logger.info(f"📁 Ingesting documents from {directory}...")

        if not directory.exists():
            logger.warning(f"Directory not found: {directory}")
            return 0

        files = list(directory.glob(file_pattern))
        logger.info(f"   Found {len(files)} files matching '{file_pattern}'")

        documents = []
        texts = []

        for file_path in files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()

                # Extract metadata from filename or content
                doc_id = file_path.stem
                metadata = self._extract_metadata_from_text(text)

                documents.append({
                    "id": doc_id,
                    "text": text,
                    "metadata": {
                        **metadata,
                        "source_file": file_path.name
                    }
                })
                texts.append(text)

            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")

        if not documents:
            logger.warning("No documents to ingest")
            return 0

        # Generate embeddings
        logger.info(f"   Generating embeddings for {len(texts)} documents...")
        embeddings = self._generate_embeddings(texts)

        # Add to public corpus
        logger.info(f"   Adding to public corpus...")
        doc_ids = await self.corpus_manager.add_to_public(
            documents=documents,
            embeddings=embeddings
        )

        logger.info(f"✅ Ingested {len(doc_ids)} documents from directory")
        return len(doc_ids)

    def _extract_metadata_from_text(self, text: str) -> Dict[str, Any]:
        """
        Extract metadata from document text using regex.

        Extracts:
        - Citations (AIR, SCC)
        - Court name
        - Year
        - Case parties
        """
        metadata = {}

        # Extract AIR citation
        air_match = re.search(r'AIR\s+(\d{4})\s+([A-Z][a-z]*)\s+(\d+)', text)
        if air_match:
            year, court_abbr, number = air_match.groups()
            metadata["year"] = int(year)
            metadata["citation_air"] = air_match.group(0)
            metadata["case_number"] = number
            metadata["court"] = self._expand_court_abbr(court_abbr)

        # Extract SCC citation
        scc_match = re.search(r'(\d{4})\s+\(\d+\)\s+SCC\s+(\d+)', text)
        if scc_match:
            year, number = scc_match.groups()
            metadata["year"] = int(year)
            metadata["citation_scc"] = scc_match.group(0)
            metadata["case_number"] = number
            metadata["court"] = "Supreme Court"

        # Extract petitioner vs respondent
        vs_match = re.search(r'([A-Z][a-z\s]+)\s+v\.?\s+([A-Z][a-z\s]+)', text)
        if vs_match:
            metadata["petitioner"] = vs_match.group(1).strip()
            metadata["respondent"] = vs_match.group(2).strip()

        return metadata

    def _expand_court_abbr(self, abbr: str) -> str:
        """Expand court abbreviation"""
        court_map = {
            "SC": "Supreme Court",
            "Del": "Delhi High Court",
            "Bom": "Bombay High Court",
            "Cal": "Calcutta High Court",
            "Mad": "Madras High Court",
            "Kar": "Karnataka High Court",
        }
        return court_map.get(abbr, abbr)


async def main():
    """Main ingestion function"""
    import argparse

    parser = argparse.ArgumentParser(description="Ingest public legal corpus")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Ingest synthetic test data"
    )
    parser.add_argument(
        "--statutes",
        type=str,
        help="Path to statutes JSON file"
    )
    parser.add_argument(
        "--directory",
        type=str,
        help="Directory with legal documents"
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.txt",
        help="File pattern for directory ingestion"
    )

    args = parser.parse_args()

    ingester = PublicCorpusIngester()
    total_ingested = 0

    # Ingest synthetic test data
    if args.synthetic:
        count = await ingester.ingest_synthetic_test_data()
        total_ingested += count

    # Ingest statutes
    if args.statutes:
        statute_path = Path(args.statutes)
        count = await ingester.ingest_statutes(statute_path)
        total_ingested += count

    # Ingest from directory
    if args.directory:
        dir_path = Path(args.directory)
        count = await ingester.ingest_from_directory(
            directory=dir_path,
            file_pattern=args.pattern
        )
        total_ingested += count

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Total documents ingested: {total_ingested}")
    logger.info(f"{'='*60}\n")

    # Show collection stats
    stats = await ingester.corpus_manager.count_docs(corpus="public")
    logger.info(f"📊 Public corpus now has {stats.get('public', 0)} documents")


if __name__ == "__main__":
    asyncio.run(main())


# End of file
