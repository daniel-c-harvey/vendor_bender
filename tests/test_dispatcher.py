from __future__ import annotations

import pytest

from invoice_importer.extraction.dispatcher import ExtractionDispatcher
from invoice_importer.extraction.types import (
    ContentType,
    SourceContent,
    UnsupportedContentTypeError,
)
from fakes import FakeExtractor


def _source(content_type: ContentType) -> SourceContent:
    return SourceContent(
        data=b"<bytes>",
        content_type=content_type,
        source_identifier=f"source-{content_type.value}",
    )


def test_dispatcher_routes_pdf_to_pdf_extractor():
    pdf_extractor = FakeExtractor(
        name="fake-pdf",
        supported_content_types=frozenset({ContentType.PDF}),
    )
    ocr_extractor = FakeExtractor(
        name="fake-ocr",
        supported_content_types=frozenset({ContentType.PNG, ContentType.JPEG}),
    )
    dispatcher = ExtractionDispatcher([pdf_extractor, ocr_extractor])

    result = dispatcher.extract(_source(ContentType.PDF))

    assert result.extractor == "fake-pdf"


def test_dispatcher_routes_png_to_ocr_extractor():
    pdf_extractor = FakeExtractor(
        name="fake-pdf",
        supported_content_types=frozenset({ContentType.PDF}),
    )
    ocr_extractor = FakeExtractor(
        name="fake-ocr",
        supported_content_types=frozenset({ContentType.PNG, ContentType.JPEG}),
    )
    dispatcher = ExtractionDispatcher([pdf_extractor, ocr_extractor])

    result = dispatcher.extract(_source(ContentType.PNG))

    assert result.extractor == "fake-ocr"


def test_dispatcher_raises_on_unsupported_content_type():
    pdf_extractor = FakeExtractor(
        name="fake-pdf",
        supported_content_types=frozenset({ContentType.PDF}),
    )
    dispatcher = ExtractionDispatcher([pdf_extractor])

    with pytest.raises(UnsupportedContentTypeError):
        dispatcher.extract(_source(ContentType.TIFF))


def test_dispatcher_raises_on_conflicting_extractors():
    a = FakeExtractor(name="a", supported_content_types=frozenset({ContentType.PDF}))
    b = FakeExtractor(name="b", supported_content_types=frozenset({ContentType.PDF}))

    with pytest.raises(ValueError):
        ExtractionDispatcher([a, b])


def test_dispatcher_supported_content_types_is_union_of_extractors():
    a = FakeExtractor(name="a", supported_content_types=frozenset({ContentType.PDF}))
    b = FakeExtractor(
        name="b",
        supported_content_types=frozenset({ContentType.PNG, ContentType.JPEG}),
    )
    dispatcher = ExtractionDispatcher([a, b])

    assert dispatcher.supported_content_types == frozenset({
        ContentType.PDF, ContentType.PNG, ContentType.JPEG,
    })