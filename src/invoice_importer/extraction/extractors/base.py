from __future__ import annotations

from typing import Protocol

from invoice_importer.extraction.types import (
    ContentType,
    ExtractedText,
    SourceContent,
)


class TextExtractor(Protocol):
    """A strategy for extracting text from a SourceContent.
    
    Implementations are typically synchronous (CPU-bound) and produce
    an ExtractedText with the raw text plus metadata.
    """
    
    @property
    def name(self) -> str:
        """Identifier for this extractor, used in ExtractedText.extractor."""
        ...
    
    @property
    def supported_content_types(self) -> frozenset[ContentType]:
        """Which content types this extractor can handle."""
        ...
    
    def extract(self, source: SourceContent) -> ExtractedText:
        """Extract text. Raises TextExtractionFailedError on failure."""
        ...