"""Layout reconstruction shared by extractors.

Both pdfplumber and rapidocr give us positioned text fragments. This module
turns a flat list of those fragments into ``TextBlock``s by clustering on
y-coordinate (lines) and then on vertical gap (paragraphs). It knows nothing
about the source format — extractors normalize their output into
:class:`PositionedText` and call :func:`cluster_into_blocks`.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from invoice_importer.extraction.types import BBox, TextBlock


@dataclass(frozen=True, slots=True)
class PositionedText:
    """A text fragment with a known bounding box. The atomic input to layout
    reconstruction. ``text`` is whatever string the extractor emitted for the
    fragment — for pdfplumber this is one word; for rapidocr it is typically
    a short multi-word phrase from one detection region."""
    text: str
    bbox: BBox


def cluster_into_blocks(
    items: list[PositionedText],
    *,
    y_tolerance: float | None = None,
    paragraph_gap_factor: float = 0.6,
) -> tuple[TextBlock, ...]:
    """Group fragments into paragraph-shaped TextBlocks in reading order.

    ``y_tolerance`` is the maximum vertical distance between two fragments'
    top edges for them to count as the same line. When ``None`` (the default),
    it is derived as 30% of the median fragment height — works for both PDF
    points and image pixels without manual tuning.

    ``paragraph_gap_factor`` controls when consecutive lines split into
    separate paragraphs: a new paragraph starts when the gap between two
    lines exceeds this fraction of the median line height. 0.6 is a
    middle-of-the-road default — tighter than a blank line, looser than
    typesetting leading.
    """
    if not items:
        return ()

    lines = _cluster_lines(items, y_tolerance=y_tolerance)
    return _cluster_paragraphs(lines, gap_factor=paragraph_gap_factor)


@dataclass(frozen=True, slots=True)
class _Line:
    """A sequence of fragments sharing a y-band, sorted left-to-right.
    ``bbox`` is the line's union bbox; ``text`` is fragments joined by a
    single space."""
    text: str
    bbox: BBox

    @property
    def top(self) -> float:
        return self.bbox[1]

    @property
    def bottom(self) -> float:
        return self.bbox[3]

    @property
    def height(self) -> float:
        return self.bottom - self.top


def _cluster_lines(
    items: list[PositionedText],
    *,
    y_tolerance: float | None,
) -> list[_Line]:
    """Group fragments sharing a y-band into lines. Output is sorted by top."""
    sorted_items = sorted(items, key=lambda it: (it.bbox[1], it.bbox[0]))

    if y_tolerance is None:
        heights = [it.bbox[3] - it.bbox[1] for it in sorted_items]
        y_tolerance = max(median(heights) * 0.3, 1.0)

    buckets: list[list[PositionedText]] = []
    for item in sorted_items:
        if buckets and abs(item.bbox[1] - buckets[-1][0].bbox[1]) <= y_tolerance:
            buckets[-1].append(item)
        else:
            buckets.append([item])

    return [_assemble_line(bucket) for bucket in buckets]


def _assemble_line(fragments: list[PositionedText]) -> _Line:
    fragments = sorted(fragments, key=lambda it: it.bbox[0])
    text = " ".join(f.text for f in fragments)
    bbox = (
        min(f.bbox[0] for f in fragments),
        min(f.bbox[1] for f in fragments),
        max(f.bbox[2] for f in fragments),
        max(f.bbox[3] for f in fragments),
    )
    return _Line(text=text, bbox=bbox)


def _cluster_paragraphs(
    lines: list[_Line],
    *,
    gap_factor: float,
) -> tuple[TextBlock, ...]:
    """Walk lines top-to-bottom; split into paragraphs at gaps wider than
    ``gap_factor * median_line_height``."""
    if not lines:
        return ()

    median_height = max(median(line.height for line in lines), 1.0)
    gap_threshold = gap_factor * median_height

    paragraphs: list[list[_Line]] = [[lines[0]]]
    for previous, current in zip(lines, lines[1:]):
        gap = current.top - previous.bottom
        if gap > gap_threshold:
            paragraphs.append([current])
        else:
            paragraphs[-1].append(current)

    return tuple(_assemble_paragraph(p) for p in paragraphs)


def _assemble_paragraph(lines: list[_Line]) -> TextBlock:
    text = "\n".join(line.text for line in lines)
    bbox = (
        min(line.bbox[0] for line in lines),
        min(line.bbox[1] for line in lines),
        max(line.bbox[2] for line in lines),
        max(line.bbox[3] for line in lines),
    )
    return TextBlock(text=text, bbox=bbox)
