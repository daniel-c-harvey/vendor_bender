from __future__ import annotations

import logging
from typing import Any

import anthropic
from anthropic.types import ToolParam, ToolChoiceToolParam, MessageParam
from pydantic import ValidationError

from invoice_importer.domain.models import Invoice
from invoice_importer.interpretation.prompts import (
    INVOICE_EXTRACTION_SYSTEM_PROMPT,
    build_user_message
)
from invoice_importer.extraction.types import (
    ExtractedText
)
from invoice_importer.interpretation.types import LLMInterpretationError

logger = logging.getLogger(__name__)

TOOL_NAME = "record_invoice"

class AnthropicInterpreter:
    """LLM interpreter using Anthropic's Claude via tool use."""

    _client: anthropic.AsyncAnthropic
    _model: str
    _max_tokens: int

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int = 4096
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens


    @property
    def name(self) -> str:
        return f"anthropic-{self._model}"


    async def interpret(self, text: ExtractedText) -> Invoice:
        tool_definition: ToolParam = {
            "name": TOOL_NAME,
            "description": "Record the structured invoice data extracted from the document.",
            "input_schema": Invoice.model_json_schema()
        }
        tool_choice: ToolChoiceToolParam = {
            "name": TOOL_NAME,
            "type": "tool",
        }
        user_content = build_user_message(text)
        message_param: MessageParam = {
            "role": "user",
            "content": user_content,
        }
        logger.info(
            "interpreting %d chars (extracted via %s) with %s",
            len(user_content),
            text.extractor,
            self._model,
        )

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=INVOICE_EXTRACTION_SYSTEM_PROMPT,
                tools=[tool_definition],
                tool_choice=tool_choice,
                messages=[message_param]
            )
        except anthropic.APIError as e:
            raise LLMInterpretationError(
                f"AnthropicAPI error: {e}",
            ) from e

        tool_input = self._extract_tool_input(response)

        try:
            return Invoice.model_validate(tool_input)
        except ValidationError as e:
            logger.warning(
                f"LLM output failed Invoice validation: %s\nRaw output: %s",
                e,
                tool_input,
            )
            raise LLMInterpretationError(
                f"LLM produced output that failed validation: {e}"
            ) from e


    @staticmethod
    def _extract_tool_input(response: anthropic.types.Message) -> dict[str, Any]:
        """Pull the tool_use block's input out of the response."""
        for block in response.content:
            if isinstance(block, anthropic.types.ToolUseBlock) and block.name == TOOL_NAME:
                return dict(block.input) if isinstance(block.input, dict) else {}

        raise LLMInterpretationError(
            f"LLM did not produce expected tool_use call."
            f"Stop reason: {response.stop_reason}"
        )