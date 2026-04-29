from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never


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
class ExtractedText:
    """Layout-preserving extraction output. Consumers render text for LLM
    consumption via :meth:`to_prompt`."""
    pages: tuple[Page, ...]
    extractor: str
    is_likely_low_quality: bool = False

    def to_prompt(self) -> str:
        """Render the document as text for an LLM.

        TextBlocks pass through; TableBlocks become GitHub-flavored Markdown
        tables. Blocks within a page are separated by blank lines. Pages are
        separated by a ``--- Page N ---`` rule only when there is more than
        one page (single-page invoices stay clean).
        """
        rendered_pages = [
            "\n\n".join(_render_block(block) for block in page.blocks)
            for page in self.pages
        ]
        if len(rendered_pages) <= 1:
            return rendered_pages[0] if rendered_pages else ""
        return "\n\n".join(
            f"--- Page {page.page_number} ---\n\n{rendered}"
            for page, rendered in zip(self.pages, rendered_pages, strict=True)
        )


def _render_block(block: Block) -> str:
    match block:
        case TextBlock(text=text):
            return text
        case TableBlock(rows=rows):
            return _render_table_gfm(rows)
        case _:
            assert_never(block)


def _render_table_gfm(rows: tuple[tuple[str, ...], ...]) -> str:
    """Render rows as a GFM table. ``|`` is escaped; embedded newlines
    become spaces (GFM cells can't span lines). Short rows are padded to
    the widest row's column count."""
    if not rows:
        return ""

    width = max(len(row) for row in rows)

    def cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")

    def render_row(row: tuple[str, ...]) -> str:
        padded = list(row) + [""] * (width - len(row))
        return "| " + " | ".join(cell(c) for c in padded) + " |"

    header = render_row(rows[0])
    separator = "| " + " | ".join("---" for _ in range(width)) + " |"
    body = [render_row(row) for row in rows[1:]]
    return "\n".join([header, separator, *body])


class ExtractionError(Exception):
    """Base class for extraction failures."""
    
    def __init__(self, message: str, *, source_identifier: str | None = None) -> None:
        self.source_identifier = source_identifier
        super().__init__(message)


class UnsupportedContentTypeError(ExtractionError):
    """Raised when a content type has no registered extractor."""


class TextExtractionFailedError(ExtractionError):
    """Raised when an extractor ran but produced no usable output."""
