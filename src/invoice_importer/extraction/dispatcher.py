from __future__ import annotations

import logging
from collections.abc import Sequence

from invoice_importer.extraction.extractors.base import TextExtractor
from invoice_importer.extraction.types import (
    ContentType,
    ExtractedText,
    SourceContent,
    UnsupportedContentTypeError
)

logger = logging.getLogger(__name__)

class ExtractionDispatcher:
    """Routes a SourceContent to the appropriate registered TextExtractor.

    Constructed with a list of extractors; builds an index by content type
    at construction time. Conflicts (multiple extractors for the same content
    type) raise immediately.
    """

    _extractors: tuple[TextExtractor, ...]
    _by_content_type: dict[ContentType, TextExtractor]

    def __init__(self, extractors: Sequence[TextExtractor]) -> None:
        self._extractors = tuple(extractors)
        self._by_content_type = self._build_index(self._extractors)


    @staticmethod
    def _build_index(extractors: Sequence[TextExtractor]) -> dict[ContentType, TextExtractor]:
        index: dict[ContentType, TextExtractor] = {}
        for extractor in extractors:
            for content_type in extractor.supported_content_types:
                if content_type in index:
                    existing = index[content_type].name
                    raise ValueError(
                        f"Multiple extractors are registered for content type {content_type}: "
                        f"{existing!r} and {extractor.name!r}"
                    )
                index[content_type] = extractor
        return index

    @property
    def supported_content_types(self) -> frozenset[ContentType]:
        """All content types the dispatcher can handle."""
        return frozenset(self._by_content_type.keys())

    def extract(self, source: SourceContent) -> ExtractedText:
        extractor = self._by_content_type.get(source.content_type)
        if extractor is None:
            supported = sorted(ct.value for ct in self._by_content_type)
            raise UnsupportedContentTypeError(
                f"No extractor registered for {source.content_type.value}. "
                f"Supported: {supported}",
                source_identifier=source.source_identifier,
            )

        logger.info(
            "extracting %s with %s",
            source.source_identifier,
            extractor.name
        )

        return extractor.extract(source)
        