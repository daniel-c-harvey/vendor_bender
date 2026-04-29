from __future__ import annotations

import logging

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from invoice_importer.domain.models import Invoice
from invoice_importer.extraction.dispatcher import ExtractionDispatcher
from invoice_importer.extraction.interpretation.base import LLMInterpreter
from invoice_importer.extraction.types import SourceContent, ExtractedText
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
    _interpreter: LLMInterpreter
    _session_factory: async_sessionmaker[AsyncSession]

    def __init__(
        self,
        *,
        dispatcher: ExtractionDispatcher,
        interpreter: LLMInterpreter,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._dispatcher = dispatcher
        self._interpreter = interpreter
        self._session_factory = session_factory

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

        # Step 1: extract text.  Synchronous (CPU-bound), wrapped via to_thread
        # in the orchestrator to avoid blocking the event loop
        extracted: ExtractedText = await asyncio.to_thread(self._dispatcher.extract, source)

        logger.info(
            "extracted %d chars from %s via %s",
            len(extracted.text),
            source.source_identifier,
            extracted.extractor,
        )

        # Step 2: interpret text into validated Invoice. Async natively.
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