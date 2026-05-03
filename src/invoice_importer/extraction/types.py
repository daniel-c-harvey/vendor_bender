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


BBox = tuple[float, float, float, float]
"""Axis-aligned bounding box: (x0, top, x1, bottom). Source-native units
(PDF points or image pixels); used only for ordering and table-area
exclusion within a single page."""


@dataclass(frozen=True, slots=True)
class TextBlock:
    """Paragraph-like run of text with its position. Multi-line content
    uses embedded ``\\n``."""
    text: str
    bbox: BBox


@dataclass(frozen=True, slots=True)
class TableBlock:
    """2D grid of cell strings with its position. ``rows[0]`` is treated
    as a header at render time."""
    rows: tuple[tuple[str, ...], ...]
    bbox: BBox


Block = TextBlock | TableBlock


@dataclass(frozen=True, slots=True)
class Page:
    """A page's blocks in reading order (top-to-bottom, left-to-right)."""
    page_number: int
    blocks: tuple[Block, ...]


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    """Layout-preserving extraction output. Pages contain blocks in reading
    order. Rendering to a flat string for LLM consumption is the
    :class:`TextNormalizer`'s responsibility, not this type's.
    """

    pages: tuple[Page, ...]
    extractor: str
    is_likely_low_quality: bool = False


@dataclass(frozen=True, slots=True)
class ExtractedText:
    """Normalized text passed to the interpreter. Produced by
    :class:`TextNormalizer` from an :class:`ExtractedDocument`. Carries the
    extractor's provenance so downstream consumers don't need to hold the
    document."""
    text: str
    extractor: str
    is_likely_low_quality: bool


class ExtractionError(Exception):
    """Base class for extraction failures."""
    
    def __init__(self, message: str, *, source_identifier: str | None = None) -> None:
        self.source_identifier = source_identifier
        super().__init__(message)


class UnsupportedContentTypeError(ExtractionError):
    """Raised when a content type has no registered extractor."""


class TextExtractionFailedError(ExtractionError):
    """Raised when an extractor ran but produced no usable output."""
