from __future__ import annotations

import io
import logging

from PIL import Image

from invoice_importer.extraction.types import (
    ContentType,
    ExtractedText,
    ExtractionError,
    SourceContent,
    TextExtractionFailedError,
)

logger = logging.getLogger(__name__)

class OcrExtractor:
    name = "rapidocr"
    supported_content_types = frozenset({
        ContentType.PNG,
        ContentType.JPEG,
        ContentType.TIFF,
        ContentType.WEBP,
    })

    def __init__(self) -> None:
        self._engine = None

    def warmup(self) -> None:
        """Initializes the OCR engine.  Call during startup."""

        if self._engine is not None:
            return

        from rapidocr_onnxruntime import RapidOCR
        logger.info("loading OCR model")
        self._engine = RapidOCR()
        logger.info("OCR model ready")

    def extract(self, source: SourceContent) -> ExtractedText:
        """Extracts text from an image/scan source."""
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

        text = self._assemble_text(result)

        if not text.strip():
            raise TextExtractionFailedError(
                "OCR produce no text from source",
                source_identifier=source.source_identifier,
            )

        return ExtractedText(
            text=text,
            page_count=1,
            extractor=self.name,
            is_likely_low_quality=False,
        )

    @staticmethod
    def _assemble_text(ocr_result: list | None) -> str:
        """Convert rapidocr's structured output into plain text.

        rapidocr returns a list of [bbox, text, confidence] entries,
        in roughly reading order. We just concatenate the text fields,
        joined by newlines so structure is at least line-preserved.
        """
        if not ocr_result:
            return ""

        lines = []
        for entry in ocr_result:
            if len(entry) >= 2:
                lines.append(str(entry[1]))

        return "\n".join(lines)

    