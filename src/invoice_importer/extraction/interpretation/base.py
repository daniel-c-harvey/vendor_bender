from __future__ import annotations

from typing import Protocol

from invoice_importer.domain.models import Invoice
from invoice_importer.extraction.types import ExtractedText

class LLMInterpreter(Protocol):
    """Strategy for converting extracted text into a validated invoice."""

    @property
    def name(self) -> str:
        """Display identifier for this interpreter"""
        ...

    async def interpret(self, text: ExtractedText) -> Invoice:
        """Parse extracted text into a validated invoice.

        Raises LLMInterpretationError on failure.
        """

        

