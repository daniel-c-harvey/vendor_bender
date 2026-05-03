from __future__ import annotations

from typing import assert_never

from invoice_importer.extraction.types import (
    Block,
    ExtractedDocument,
    ExtractedText,
    TableBlock,
    TextBlock
)

class TextNormalizer:
    """Render an :class:`ExtractedDocument` into the normalized
    :class:`ExtractedText` consumed by the interpreter.

    TextBlocks pass through; TableBlocks become GitHub-flavored Markdown
    tables. Blocks within a page are separated by blank lines. Pages are
    separated by a ``--- Page N ---`` rule only when there is more than
    one page (single-page invoices stay clean).
    """

    def normalize(self, document: ExtractedDocument) -> ExtractedText:
        rendered_pages = [
            "\n\n".join(_render_block(block) for block in page.blocks)
            for page in document.pages
        ]
        if len(rendered_pages) <= 1:
            text = rendered_pages[0] if rendered_pages else ""
        else:
            text = "\n\n".join(
                f"--- Page {page.page_number} ---\n\n{rendered}"
                for page, rendered in zip(
                    document.pages, rendered_pages, strict=True
                )
            )
        return ExtractedText(
            text=text,
            extractor=document.extractor,
            is_likely_low_quality=document.is_likely_low_quality,
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