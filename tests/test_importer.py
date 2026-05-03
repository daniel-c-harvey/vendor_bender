from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from invoice_importer.domain.errors import DuplicateContentError
from invoice_importer.domain.models import Invoice
from invoice_importer.extraction.dispatcher import ExtractionDispatcher
from invoice_importer.extraction.normalizer import TextNormalizer
from invoice_importer.extraction.types import (
    ContentType,
    SourceContent,
    UnsupportedContentTypeError,
)
from invoice_importer.orchestration.importer import InvoiceImporter

from factories import make_invoice
from fakes import FakeExtractor, FakeInterpreter


def _build_importer(
        session_factory: async_sessionmaker[AsyncSession],
        *,
        invoice: Invoice
) -> InvoiceImporter:
    return InvoiceImporter(
        dispatcher=ExtractionDispatcher([
            FakeExtractor(
                name="fake-pdf",
                supported_content_types=frozenset({ContentType.PDF}),
            ),
        ]),
        normalizer=TextNormalizer(),
        interpreter=FakeInterpreter(
            name="fake-llm",
            invoice=invoice,
        ),
        session_factory=session_factory,
    )


def _pdf_source(*, content: bytes = b"<pdf bytes>", identifier: str = "file://x.pdf") -> SourceContent:
    return SourceContent(
        data=content,
        content_type=ContentType.PDF,
        source_identifier=identifier,
    )


async def test_import_invoice_end_to_end(session_factory: async_sessionmaker[AsyncSession]):
    invoice = make_invoice(invoice_number="INV-PIPE-1")
    importer = _build_importer(session_factory=session_factory, invoice=invoice)

    result = await importer.import_invoice(_pdf_source())

    assert result.invoice_number == "INV-PIPE-1"
    assert result.vendor.name == invoice.vendor.name
    assert result.currency == invoice.currency
    assert result.grand_total == invoice.grand_total
    assert len(result.line_items) == len(invoice.line_items)


async def test_import_invoice_propagates_unsupported_content_type(session_factory: async_sessionmaker[AsyncSession]):
    importer = _build_importer(session_factory=session_factory, invoice=make_invoice())

    png_source = SourceContent(
        data=b"<png bytes>",
        content_type=ContentType.PNG,
        source_identifier="file://x.png",
    )

    with pytest.raises(UnsupportedContentTypeError):
        await importer.import_invoice(png_source)


async def test_import_invoice_raises_duplicate_content_on_second_import(
        session_factory: async_sessionmaker[AsyncSession]
):
    invoice = make_invoice(invoice_number="INV-DUP-1")
    importer = _build_importer(session_factory=session_factory, invoice=invoice)
    content = b"identical bytes"

    await importer.import_invoice(_pdf_source(content=content))

    with pytest.raises(DuplicateContentError):
        await importer.import_invoice(_pdf_source(content=content))