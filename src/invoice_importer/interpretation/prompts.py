from __future__ import annotations

from pathlib import Path

from invoice_importer.extraction.types import ExtractedText

_PROMPTS_PATH = Path(__file__).parent / "prompts"

def _load_prompt(prompt_name: str) -> str:
    return (_PROMPTS_PATH / prompt_name).read_text(encoding="utf-8")

INVOICE_EXTRACTION_SYSTEM_PROMPT = _load_prompt("invoice_extraction_system_prompt.txt")

def build_user_message(extracted: ExtractedText) -> str:
    """Wrap the normalized extraction text into the user message for the LLM."""
    return (
        f"<invoice_document>{extracted.text}</invoice_document>"
        "Extract the structured invoice data using the record_invoice tool."
    )
