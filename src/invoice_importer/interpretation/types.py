from invoice_importer.extraction.types import ExtractionError


class LLMInterpretationError(ExtractionError):
    """Raised when the LLM fails to produce a valid Invoice from extracted text."""