from __future__ import annotations

from typing import Protocol

from invoice_importer.extraction.types import (
    ContentType,
    ExtractedDocument,
    SourceContent,
)


class TextExtractor(Protocol):
    """A strategy for extracting text from a SourceContent.

    Implementations are typically synchronous (CPU-bound) and produce
    an ExtractedDocument with layout-preserving blocks plus metadata.
    """

    @property
    def name(self) -> str:
        """Identifier for this extractor, used in ExtractedDocument.extractor."""
        ...
    
    @property
    def supported_content_types(self) -> frozenset[ContentType]:
        """Which content types this extractor can handle."""
        ...
    
    def extract(self, source: SourceContent) -> ExtractedDocument:
        """Extract text. Raises TextExtractionFailedError on failure."""
        ...