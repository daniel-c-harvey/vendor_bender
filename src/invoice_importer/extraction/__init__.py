from invoice_importer.extraction.dispatcher import ExtractionDispatcher
from invoice_importer.extraction.extractors.base import TextExtractor
from invoice_importer.extraction.normalizer import TextNormalizer
from invoice_importer.extraction.types import (
    BBox,
    Block,
    ContentType,
    ExtractedDocument,
    ExtractedText,
    ExtractionError,
    Page,
    SourceContent,
    TableBlock,
    TextBlock,
    TextExtractionFailedError,
    UnsupportedContentTypeError,
)

# Concrete extractors (PdfTextExtractor, OcrExtractor) are intentionally not
# re-exported here — re-exporting would force pdfplumber / rapidocr to load
# on any import from this layer. Reach them at their deep paths instead.

__all__ = [
    "BBox",
    "Block",
    "ContentType",
    "ExtractedDocument",
    "ExtractedText",
    "ExtractionDispatcher",
    "ExtractionError",
    "Page",
    "SourceContent",
    "TableBlock",
    "TextBlock",
    "TextExtractionFailedError",
    "TextExtractor",
    "TextNormalizer",
    "UnsupportedContentTypeError",
]
