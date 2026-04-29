from __future__ import annotations

import io
import logging
from typing import Any, Self

from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from invoice_importer.extraction.layout import PositionedText, cluster_into_blocks
from invoice_importer.extraction.types import (
    BBox,
    ContentType,
    ExtractedText,
    ExtractionError,
    Page,
    SourceContent,
    TextExtractionFailedError,
)

logger = logging.getLogger(__name__)


class OcrExtractor:
    """Extracts layout-preserving text from a single-page image via rapidocr.

    rapidocr returns a list of (quad, text, confidence) detections where
    ``quad`` is four corner points (potentially rotated for skewed text).
    We axis-align each quad, group fragments into paragraph-shaped
    TextBlocks via the shared layout pipeline, and emit a single
    one-page :class:`ExtractedText`. No table detection — that is a much
    harder problem from raw OCR bboxes than it is from a digital PDF.
    """

    name = "rapidocr"
    supported_content_types = frozenset({
        ContentType.PNG,
        ContentType.JPEG,
        ContentType.TIFF,
        ContentType.WEBP,
    })

    _engine: RapidOCR | None

    def __init__(self) -> None:
        self._engine = None

    def warmup(self) -> Self:
        """Initialize the OCR engine. Call during startup."""
        if self._engine is not None:
            return self

        logger.info("loading OCR model")
        self._engine = RapidOCR()
        logger.info("OCR model ready")
        return self

    def extract(self, source: SourceContent) -> ExtractedText:
        if self._engine is None:
            raise RuntimeError(
                "OCR engine not initialized.  "
                "warmup() must be called before using extract()"
            )

        if source.content_type not in self.supported_content_types:
            raise ExtractionError(
                f"OcrExtractor cannot handle {source.content_type}",
                source_identifier=source.source_identifier,
            )

        try:
            image = Image.open(io.BytesIO(source.data))
            image.load()
        except Exception as e:
            raise TextExtractionFailedError(
                f"Could not decode image: {e}",
                source_identifier=source.source_identifier,
            ) from e

        try:
            result, _elapsed = self._engine(image)
        except Exception as e:
            raise TextExtractionFailedError(
                f"OCR engine failed: {e}",
                source_identifier=source.source_identifier,
            ) from e

        positioned = _to_positioned(result)
        if not positioned:
            raise TextExtractionFailedError(
                "OCR produced no text from source",
                source_identifier=source.source_identifier,
            )

        blocks = cluster_into_blocks(positioned)
        page = Page(page_number=1, blocks=tuple(blocks))

        return ExtractedText(
            pages=(page,),
            extractor=self.name,
            is_likely_low_quality=False,
        )


def _to_positioned(ocr_result: list[Any] | None) -> list[PositionedText]:
    """Normalize rapidocr's ``[quad, text, confidence]`` entries into
    :class:`PositionedText`. ``quad`` is converted to an axis-aligned bbox."""
    if not ocr_result:
        return []

    out: list[PositionedText] = []
    for entry in ocr_result:
        if len(entry) < 2:
            continue
        quad, text = entry[0], str(entry[1])
        bbox = _quad_to_aabb(quad)
        if bbox is None:
            continue
        out.append(PositionedText(text=text, bbox=bbox))
    return out


def _quad_to_aabb(quad: Any) -> BBox | None:
    """Collapse a 4-corner quadrilateral to its axis-aligned bounding box.
    Returns None when the quad shape is unrecognized — defensive against
    rapidocr versions that change their output schema."""
    try:
        xs = [float(point[0]) for point in quad]
        ys = [float(point[1]) for point in quad]
    except (TypeError, ValueError, IndexError):
        return None
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))
