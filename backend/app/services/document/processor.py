import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Any, Optional
import re
from datetime import datetime
import logging

from app.core.config import settings
from app.services.cognita.client import get_cognita_client

logger = logging.getLogger(__name__)


class LegalMetadataExtractor:
    """
    Custom Legal Metadata Extractor for Indian Law
    This is what YOU build - Cognita doesn't understand Indian legal context
    """

    def extract_citation(self, text: str) -> Optional[str]:
        """Extract Indian legal citation (AIR, SCC, etc.)"""
        patterns = [
            r'AIR\s+\d{4}\s+[A-Z]+\s+\d+',
            r'\(\d{4}\)\s+\d+\s+SCC\s+\d+',
            r'\d{4}\s+SCC\s+\(\w+\)\s+\d+',
            r'\d{4}\s+SCR\s+\d+',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    def extract_court(self, text: str) -> Optional[str]:
        """Extract court name"""
        court_patterns = [
            r'(SUPREME COURT OF INDIA)',
            r'(HIGH COURT OF [A-Z\s]+)',
            r'([A-Z\s]+ HIGH COURT)',
        ]

        for pattern in court_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                court_name = match.group(1).title()

                # Determine court level
                if 'SUPREME COURT' in court_name.upper():
                    return court_name, 'Supreme Court'
                elif 'HIGH COURT' in court_name.upper():
                    return court_name, 'High Court'
                else:
                    return court_name, 'District Court'

        return None, None

    def extract_judges(self, text: str) -> List[str]:
        """Extract judge names from CORAM section"""
        coram_pattern = r'CORAM:\s*([A-Z\s,\.]+?)(?:\n|\r|JUDGMENT)'
        match = re.search(coram_pattern, text, re.IGNORECASE)

        if match:
            judges_text = match.group(1).strip()
            judges = [j.strip() for j in judges_text.split(',')]
            return judges[:5]  # Limit to 5

        return []

    def extract_bench_strength(self, text: str) -> Optional[int]:
        """Determine bench strength"""
        judges = self.extract_judges(text)
        return len(judges) if judges else None

    def extract_dates(self, text: str) -> Dict[str, Optional[str]]:
        """Extract decision and filing dates"""
        dates = {}

        # Decision date patterns
        decision_patterns = [
            r'DATED[:\s]+(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
            r'JUDGMENT\s+DATED[:\s]+(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
        ]

        for pattern in decision_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                day, month, year = match.groups()
                dates['decision_date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                break

        return dates

    def extract_parties(self, text: str) -> List[str]:
        """Extract party names"""
        # Look for party names in first 30 lines
        lines = text.split('\n')[:30]
        parties = []

        for line in lines:
            if 'vs' in line.lower() or 'v.' in line.lower() or 'versus' in line.lower():
                parties.append(line.strip())
                if len(parties) >= 2:
                    break

        return parties

    def extract_acts_and_sections(self, text: str) -> Dict[str, List[str]]:
        """Extract statutes and sections cited"""
        acts = set()
        sections = set()

        # Section patterns
        section_patterns = [
            r'Section\s+(\d+[A-Z]?)\s+(?:of\s+)?(?:the\s+)?([A-Z][A-Za-z\s,]+(?:Act|Code))',
            r'Article\s+(\d+[A-Z]?)\s+of\s+(?:the\s+)?Constitution',
        ]

        for pattern in section_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) == 2:
                    section_num, act_name = match
                    acts.add(act_name.strip())
                    sections.add(f"Section {section_num} of {act_name.strip()}")
                else:
                    sections.add(f"Article {match[0]} of Constitution")
                    acts.add("Constitution of India")

        return {
            'acts_cited': list(acts)[:10],
            'sections_cited': list(sections)[:20]
        }

    def extract_precedents(self, text: str) -> List[str]:
        """Extract case citations referenced"""
        citation_patterns = [
            r'AIR\s+\d{4}\s+[A-Z]+\s+\d+',
            r'\(\d{4}\)\s+\d+\s+SCC\s+\d+',
        ]

        citations = set()
        for pattern in citation_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            citations.update(matches)

        return list(citations)[:20]  # Limit to 20

    def segment_judgment(self, text: str) -> Dict[str, str]:
        """Segment judgment into parts"""
        segments = {}

        section_patterns = {
            'facts': r'(FACTS?|BACKGROUND|BRIEF FACTS)',
            'issues': r'(ISSUES?|POINTS? FOR CONSIDERATION|QUESTIONS?)',
            'arguments': r'(ARGUMENTS?|SUBMISSIONS?|CONTENTIONS?)',
            'held': r'(HELD|JUDGMENT|DECISION|ORDER)',
        }

        section_positions = []
        for segment_type, pattern in section_patterns.items():
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            for match in matches:
                section_positions.append((match.start(), segment_type))

        section_positions.sort()

        for i, (start, segment_type) in enumerate(section_positions):
            if i + 1 < len(section_positions):
                end = section_positions[i + 1][0]
            else:
                end = len(text)

            segment_text = text[start:end].strip()

            if segment_type not in segments:
                segments[segment_type] = segment_text

        if not segments:
            segments['full_text'] = text

        return segments

    def extract_all(self, text: str) -> Dict[str, Any]:
        """Extract all legal metadata"""
        citation = self.extract_citation(text)
        court_name, court_level = self.extract_court(text)
        judges = self.extract_judges(text)
        bench_strength = self.extract_bench_strength(text)
        dates = self.extract_dates(text)
        parties = self.extract_parties(text)
        acts_sections = self.extract_acts_and_sections(text)
        precedents = self.extract_precedents(text)
        segments = self.segment_judgment(text)

        metadata = {
            'citation': citation,
            'court_name': court_name,
            'court_level': court_level,
            'judges': judges,
            'bench_strength': bench_strength,
            'parties': parties,
            'precedents_cited': precedents,
            **dates,
            **acts_sections,
        }

        # Remove None values
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return {
            'metadata': metadata,
            'segments': segments
        }


class HybridDocumentProcessor:
    """
    Hybrid Processor:
    - Uses Cognita for: PDF parsing, chunking, indexing
    - Uses Custom code for: Legal metadata extraction, segmentation
    """

    def __init__(self):
        self.cognita_client = get_cognita_client() if settings.USE_COGNITA_FOR_PARSING else None
        self.metadata_extractor = LegalMetadataExtractor()

    async def process_document(
        self,
        file_path: str,
        collection_name: str = "legal_documents",
        document_type: str = "judgment",
    ) -> Dict[str, Any]:
        """
        Process document using hybrid approach

        1. Cognita parses PDF -> gets text + chunks
        2. YOU extract legal metadata -> Indian legal context
        3. Combine both -> rich legal document
        """
        logger.info(f"Processing document (Hybrid mode): {file_path}")
        logger.info(f"DEBUG: USE_COGNITA_FOR_PARSING = {settings.USE_COGNITA_FOR_PARSING}")
        logger.info(f"DEBUG: cognita_client exists = {self.cognita_client is not None}")

        # Step 1: Use Cognita for parsing and chunking
        if self.cognita_client and settings.USE_COGNITA_FOR_PARSING:
            try:
                logger.info("DEBUG: Attempting Cognita processing...")
                cognita_result = await self.cognita_client.upload_document(
                    file_path=file_path,
                    collection_name=collection_name,
                    document_metadata={'document_type': document_type}
                )

                # Extract full text from chunks
                full_text = "\n".join([
                    chunk.get('content', '')
                    for chunk in cognita_result.get('chunks', [])
                ])

                cognita_metadata = cognita_result.get('metadata', {})
                chunks = cognita_result.get('chunks', [])

                logger.info(f"✓ Cognita processed: {len(chunks)} chunks")

            except Exception as e:
                logger.error(f"Cognita processing failed: {e}")
                logger.info("Falling back to manual processing...")
                full_text = self._extract_text_fallback(file_path)
                chunks = self._chunk_text_simple(full_text)
                cognita_metadata = {}

        else:
            # Fallback: Manual processing
            logger.info("DEBUG: Using fallback manual processing")
            logger.info(f"DEBUG: About to extract text from {file_path}")
            try:
                full_text = self._extract_text_fallback(file_path)
                logger.info(f"DEBUG: Text extracted, length = {len(full_text)}")
            except Exception as e:
                logger.error(f"DEBUG: Text extraction failed: {e}", exc_info=True)
                raise
            
            logger.info("DEBUG: About to chunk text")
            try:
                chunks = self._chunk_text_simple(full_text)
                logger.info(f"DEBUG: Chunking complete, got {len(chunks)} chunks")
            except Exception as e:
                logger.error(f"DEBUG: Chunking failed: {e}", exc_info=True)
                raise
            
            cognita_metadata = {}

        # Step 2: Extract LEGAL-SPECIFIC metadata (YOUR custom code)
        logger.info("DEBUG: Starting legal metadata extraction...")
        try:
            legal_data = self.metadata_extractor.extract_all(full_text)
            legal_metadata = legal_data['metadata']
            segments = legal_data['segments']
            logger.info(f"DEBUG: Legal metadata extracted successfully")
        except Exception as e:
            logger.error(f"DEBUG: Legal metadata extraction failed: {e}", exc_info=True)
            raise

        logger.info(f"✓ Extracted legal metadata: {legal_metadata.get('citation', 'No citation')}")

        # Step 3: Combine Cognita's output + YOUR legal metadata
        logger.info("DEBUG: Combining metadata...")
        combined_metadata = {
            **cognita_metadata,
            **legal_metadata,
            'document_type': document_type,
            'file_path': file_path,
            'processing_method': 'hybrid' if self.cognita_client else 'manual'
        }

        result = {
            'full_text': full_text,
            'chunks': chunks if isinstance(chunks, list) else [{'content': c} for c in chunks],
            'metadata': combined_metadata,
            'segments': segments,
            'num_chunks': len(chunks),
            'num_precedents': len(legal_metadata.get('precedents_cited', [])),
        }

        logger.info(f"✓ Processing complete: {len(chunks)} chunks, {len(segments)} segments")
        logger.info("DEBUG: Returning result from process_document")
        return result

    def _extract_text_fallback(self, file_path: str) -> str:
        """Fallback PDF extraction if Cognita fails"""
        logger.info(f"DEBUG: Opening PDF with PyMuPDF: {file_path}")
        try:
            doc = fitz.open(file_path)
            logger.info(f"DEBUG: PDF opened, pages: {len(doc)}")
            text_parts = []
            for page_num, page in enumerate(doc):
                logger.info(f"DEBUG: Extracting page {page_num + 1}")
                text_parts.append(page.get_text())
            doc.close()
            logger.info(f"DEBUG: All pages extracted, total parts: {len(text_parts)}")
            return "\n".join(text_parts)
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}", exc_info=True)
            raise

    def _chunk_text_simple(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Simple chunking fallback - guaranteed to terminate"""
        logger.info(f"DEBUG: Chunking text of length {len(text)}")
        logger.info(f"DEBUG: Chunk size: {chunk_size}, overlap: {overlap}")
        
        if not text or len(text) == 0:
            logger.warning("DEBUG: Empty text provided for chunking")
            return []
        
        chunks = []
        text_length = len(text)
        position = 0
        chunk_count = 0
        max_chunks = 1000  # Safety limit
        
        while position < text_length and chunk_count < max_chunks:
            chunk_count += 1
            logger.info(f"DEBUG: Creating chunk {chunk_count}, position: {position}/{text_length}")
            
            # Calculate chunk end
            chunk_end = min(position + chunk_size, text_length)
            
            # Extract chunk
            chunk = text[position:chunk_end].strip()
            
            if chunk:  # Only add non-empty chunks
                chunks.append(chunk)
                logger.info(f"DEBUG: Chunk {chunk_count} added, length: {len(chunk)}")
            
            # Move position forward
            # Ensure we always make progress
            next_position = position + chunk_size - overlap
            if next_position <= position:  # Safety check to prevent infinite loop
                next_position = position + 1
            
            position = next_position
            
            # If we're within one chunk size of the end, just take the rest
            if text_length - position < chunk_size:
                if position < text_length:
                    final_chunk = text[position:].strip()
                    if final_chunk and final_chunk not in chunks:  # Avoid duplicates
                        chunks.append(final_chunk)
                        logger.info(f"DEBUG: Final chunk added, length: {len(final_chunk)}")
                break
        
        logger.info(f"DEBUG: Chunking complete - created {len(chunks)} chunks")
        return chunks


_processor = None


def get_document_processor() -> HybridDocumentProcessor:
    """Get hybrid document processor singleton"""
    global _processor
    if _processor is None:
        _processor = HybridDocumentProcessor()
    return _processor