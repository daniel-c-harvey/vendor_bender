from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from invoice_importer.config import get_settings, Settings
from invoice_importer.extraction.dispatcher import ExtractionDispatcher
from invoice_importer.extraction.extractors.ocr import OcrExtractor
from invoice_importer.extraction.extractors.pdf import PdfTextExtractor
from invoice_importer.extraction.interpretation.anthropic_client import AnthropicInterpreter
from invoice_importer.extraction.interpretation.base import LLMInterpreter
from invoice_importer.extraction.interpretation.llama_cpp_client import LlamaCppInterpreter
from invoice_importer.orchestration.importer import InvoiceImporter
from invoice_importer.storage.db import make_engine, make_session_factory

logger = logging.getLogger(__name__)


def build_extraction() -> ExtractionDispatcher:
    pdf_extractor = PdfTextExtractor()
    ocr_extractor = OcrExtractor()
    ocr_extractor.warmup()

    return ExtractionDispatcher([pdf_extractor, ocr_extractor])


def build_interpreter(settings: Settings) -> LLMInterpreter:
    if settings.use_local_llm:
        return LlamaCppInterpreter(
            model_path=settings.llama_model_path,
            n_ctx=settings.llama_n_ctx,
            n_gpu_layers=settings.llama_n_gpu_layers,
            seed=settings.llama_seed
        ).warmup()
    elif settings.anthropic_api_key is not None:
        return AnthropicInterpreter(
            api_key=settings.anthropic_api_key.get_secret_value(),
            model=settings.anthropic_model,
        )

    raise ValueError("the settings are not configured for any interpreter")


def build_session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(
        make_engine(settings.database_url)
    )


def build_importer() -> InvoiceImporter:
    """Construct the InvoiceImporter with dependencies.
    
    This is the composition root. All wiring happens here in dependency order.
    """
    
    settings = get_settings()

    return InvoiceImporter(
        dispatcher=build_extraction(),
        interpreter=build_interpreter(settings),
        session_factory=build_session_factory(settings),
    )