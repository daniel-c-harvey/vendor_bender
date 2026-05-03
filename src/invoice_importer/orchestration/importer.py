from __future__ import annotations

import logging

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from invoice_importer.domain.models import Invoice
from invoice_importer.extraction.dispatcher import ExtractionDispatcher
from invoice_importer.extraction.normalizer import TextNormalizer
from invoice_importer.extraction.types import (
    ExtractedText,
    SourceContent,
)
from invoice_importer.interpretation.base import LLMInterpreter
from invoice_importer.storage import repository
from invoice_importer.storage.db import transactional_session


logger = logging.getLogger(__name__)


class InvoiceImporter:
    """End-to-end invoice import: extraction -> interpretation -> persistence

    Composes the extraction and storage layers into a single transactional
    operation. Constructed once at application startup with all dependencies;
    reused for every invoice.
    """

    _dispatcher: ExtractionDispatcher
    _normalizer: TextNormalizer
    _interpreter: LLMInterpreter
    _session_factory: async_sessionmaker[AsyncSession]

    def __init__(
        self,
        *,
        dispatcher: ExtractionDispatcher,
        normalizer: TextNormalizer,
        interpreter: LLMInterpreter,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._dispatcher = dispatcher
        self._normalizer = normalizer
        self._interpreter = interpreter
        self._session_factory = session_factory

    def _extract_and_normalize(self, source: SourceContent) -> ExtractedText:
        """Run the two sync extraction stages together so the orchestrator
        crosses the async-sync boundary exactly once. Logs the document's
        block/page detail here because that's the only place the document
        exists; callers see only the normalized text."""
        document = self._dispatcher.extract(source)
        text = self._normalizer.normalize(document)
        logger.info(
            "extracted %d blocks across %d pages from %s via %s; %d chars normalized",
            sum(len(page.blocks) for page in document.pages),
            len(document.pages),
            source.source_identifier,
            document.extractor,
            len(text.text),
        )
        return text

    async def import_invoice(self, source: SourceContent) -> Invoice:
        """Import a single invoice from raw content.

        Raises:
            ExtractionError: text extraction failed
            LLMInterpretationError: LLM produced output that couldn't be validated
            DuplicateContentError: this exact content was already imported
            DuplicateInvoiceError: vendor + invoice_number already exists
        """
        logger.info(
            "importing invoice from %s (%s, %d bytes)",
            source.source_identifier,
            source.content_type.value,
            len(source.data),
        )

        # Step 1: extract + normalize. Both stages are sync (CPU-bound) and
        # paired behind one to_thread so the orchestrator crosses the async-
        # sync boundary exactly once.
        extracted = await asyncio.to_thread(self._extract_and_normalize, source)

        # Step 2: interpret normalized text into validated Invoice. Async natively.
        invoice = await self._interpreter.interpret(extracted)

        logger.info(
            "interpreted invoice %s from vendor %s, total %s %s",
            invoice.invoice_number,
            invoice.vendor.name,
            invoice.grand_total,
            invoice.currency.value
        )

        # Step 3: persist within a transaction. Re-load to return a fully
        # hydrated domain Invoice with any DB-generated fields applied.
        async with transactional_session(self._session_factory) as session:
            invoice_row = await repository.save_invoice(
                session,
                invoice,
                source_identifier=source.source_identifier,
                content=source.data
            )
            saved = await repository.get_invoice_by_id(session, invoice_row.id)

        logger.info(
            "persisted invoice %s as id=%d",
            saved.invoice_number,
            invoice_row.id,
        )
        return saved