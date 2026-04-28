from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ContentType(StrEnum):
    """Recognized input formats for invoice extraction."""
    PDF = "application/pdf"
    PNG = "image/png"
    JPEG = "image/jpeg"
    TIFF = "image/tiff"
    WEBP = "image/webp"


@dataclass(frozen=True, slots=True)
class SourceContent:
    """A document to be extracted, with its provenance and type."""
    data: bytes
    content_type: ContentType
    source_identifier: str    # file path, URL, email message-id, etc.


@dataclass(frozen=True, slots=True)
class ExtractedText:
    """Raw text extracted from a document, plus metadata about extraction."""
    text: str
    page_count: int
    extractor: str             # name of the extractor used, for diagnostics
    is_likely_low_quality: bool = False    # heuristic flag


class ExtractionError(Exception):
    """Base class for extraction failures."""
    
    def __init__(self, message: str, *, source_identifier: str | None = None) -> None:
        self.source_identifier = source_identifier
        super().__init__(message)


class UnsupportedContentTypeError(ExtractionError):
    """Raised when a content type has no registered extractor."""


class TextExtractionFailedError(ExtractionError):
    """Raised when an extractor ran but produced no usable output."""


class LLMInterpretationError(ExtractionError):
    """Raised when the LLM fails to produce a valid Invoice from extracted text."""