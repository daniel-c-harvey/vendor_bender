from __future__ import annotations

import io
import logging
from typing import Any

import pdfplumber
from pdfplumber.page import Page as PdfPage

from invoice_importer.extraction.layout import PositionedText, cluster_into_blocks
from invoice_importer.extraction.types import (
    BBox,
    Block,
    ContentType,
    ExtractedText,
    ExtractionError,
    Page,
    SourceContent,
    TableBlock,
    TextBlock,
    TextExtractionFailedError,
)

logger = logging.getLogger(__name__)

_LOW_QUALITY_PAGE_CHAR_THRESHOLD = 50
"""Below this many text chars on the largest page, we flag the document as
likely a scan that pdfplumber can't read — caller may retry via OCR."""


class PdfTextExtractor:
    """Extracts layout-preserving text from digital PDFs using pdfplumber.

    Per page: detect tables first (pdfplumber's table-finder is good for
    bordered tables; less reliable for borderless ones), then cluster the
    remaining words into paragraph-shaped TextBlocks. Tables and text blocks
    are merged into a single reading-ordered sequence.
    """

    name = "pdfplumber"
    supported_content_types = frozenset({ContentType.PDF})

    def extract(self, source: SourceContent) -> ExtractedText:
        if source.content_type != ContentType.PDF:
            raise ExtractionError(
                f"PdfTextExtractor cannot handle {source.content_type}",
                source_identifier=source.source_identifier,
            )

        try:
            pages = self._extract_pages(source.data)
        except Exception as e:
            raise TextExtractionFailedError(
                "pdfplumber failed to read pdf",
                source_identifier=source.source_identifier,
            ) from e

        if not pages or all(not page.blocks for page in pages):
            raise TextExtractionFailedError(
                "pdfplumber extracted no text from PDF (likely scanned or image only)",
                source_identifier=source.source_identifier,
            )

        largest_page_chars = max(_count_chars(page) for page in pages)
        is_likely_low_quality = largest_page_chars < _LOW_QUALITY_PAGE_CHAR_THRESHOLD
        if is_likely_low_quality:
            logger.warning(
                "PDF %s had fewer than %d characters (%d) on the largest page; likely scanned",
                source.source_identifier,
                _LOW_QUALITY_PAGE_CHAR_THRESHOLD,
                largest_page_chars,
            )

        return ExtractedText(
            pages=tuple(pages),
            extractor=self.name,
            is_likely_low_quality=is_likely_low_quality,
        )

    @staticmethod
    def _extract_pages(data: bytes) -> list[Page]:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return [_extract_page(page, page_number=i + 1) for i, page in enumerate(pdf.pages)]


def _extract_page(page: PdfPage, *, page_number: int) -> Page:
    table_blocks = _extract_table_blocks(page)
    table_bboxes = [block.bbox for block in table_blocks]

    word_dicts = page.extract_words() or []
    words_outside_tables = [w for w in word_dicts if not _word_in_any(w, table_bboxes)]
    text_blocks = cluster_into_blocks(
        [_word_to_positioned(w) for w in words_outside_tables]
    )

    blocks: list[Block] = [*table_blocks, *text_blocks]
    blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
    return Page(page_number=page_number, blocks=tuple(blocks))


def _extract_table_blocks(page: PdfPage) -> list[TableBlock]:
    blocks: list[TableBlock] = []
    for table in page.find_tables():
        rows_raw = table.extract()
        if not rows_raw:
            continue
        rows = tuple(
            tuple((cell or "").strip() for cell in row)
            for row in rows_raw
        )
        bbox: BBox = (
            float(table.bbox[0]),
            float(table.bbox[1]),
            float(table.bbox[2]),
            float(table.bbox[3]),
        )
        blocks.append(TableBlock(rows=rows, bbox=bbox))
    return blocks


def _word_to_positioned(word: dict[str, Any]) -> PositionedText:
    return PositionedText(
        text=str(word["text"]),
        bbox=(
            float(word["x0"]),
            float(word["top"]),
            float(word["x1"]),
            float(word["bottom"]),
        ),
    )


def _word_in_any(word: dict[str, Any], bboxes: list[BBox]) -> bool:
    """A word is "in" a table when its center point falls inside the table's
    bbox. Center-point test (rather than corner-overlap) avoids spuriously
    excluding words whose bbox grazes a table border."""
    if not bboxes:
        return False
    cx = (float(word["x0"]) + float(word["x1"])) / 2
    cy = (float(word["top"]) + float(word["bottom"])) / 2
    return any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in bboxes)


def _count_chars(page: Page) -> int:
    total = 0
    for block in page.blocks:
        if isinstance(block, TextBlock):
            total += len(block.text)
        else:
            total += sum(len(cell) for row in block.rows for cell in row)
    return total
