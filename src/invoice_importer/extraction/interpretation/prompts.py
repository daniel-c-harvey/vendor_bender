from __future__ import annotations

from io import FileIO
from pathlib import Path

_PROMPTS_PATH = Path(__file__).parent / "prompts"

def _load_prompt(prompt_name: str) -> str:
    with FileIO(_PROMPTS_PATH / prompt_name) as file:
        return str(file.read())

INVOICE_EXTRACTION_SYSTEM_PROMPT = _load_prompt("invoice_extraction_system_prompt.txt")

def build_user_message(text: str) -> str:
    """Wrap extracted text into the user message for the LLM."""
    return f"""<invoice_document>""" \
           f"""{text}""" \
           """</invoice_document>""" \
           """Extract the structured invoice data using the record_invoice tool."""
