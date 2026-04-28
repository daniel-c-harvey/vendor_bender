from __future__ import annotations

import io
import logging

import pdfplumber

from invoice_importer.extraction.types import (
    ContentType,
    ExtractedText,
    ExtractionError,
    SourceContent,
    TextExtractionFailedError
)

logger = logging.getLogger(__name__)

class PdfTextExtractor:
    """Extracts text from digital (text-based) PDFs using pdfplumber"""

    name = "pdfplumber"
    supported_content_types = frozenset({ContentType.PDF})

    def extract(self, source: SourceContent) -> ExtractedText:
        if source.content_type != ContentType.PDF:
            raise ExtractionError(
                f"PdfTextExtractor cannot handle {source.content_type}",
                source_identifier=source.source_identifier
            )
        
        try:
            pages_text = self._extract_pages(source.data)
        except Exception as e:
            raise TextExtractionFailedError(
                f"pdfplumber failed to read pdf",
                source_identifier=source.source_identifier
            ) from e
        
        text = "\n\n".join(pages_text)
        page_count = len(pages_text)

        # TODO abstract out the heuristics
        # Heuristic: very little text per page suggests a scanned PDF
        # where the page is mostly images, not extractable text.
        largest_page_length = max([len(page_text) for page_text in pages_text])
        is_likely_low_quality = largest_page_length < 50

        if is_likely_low_quality:
            logger.warning(
                "PDF %s had fewer than 50 characters (%d) on the largest page ; likely scanned",
                source.source_identifier,
                largest_page_length
            )

        if not text.strip():
            raise TextExtractionFailedError(
                "pdfplumber extracted no text from PDF (likely scanned or image only)",
                source_identifier=source.source_identifier
            )
        
        return ExtractedText(
            text=text,
            page_count=page_count,
            extractor=self.name,
            is_likely_low_quality=is_likely_low_quality
        )

    @staticmethod
    def _extract_pages(data: bytes) -> list[str]:
        """Extract text from each page, returning a list of page strings"""

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return [page.extract_text() or "" for page in pdf.pages]