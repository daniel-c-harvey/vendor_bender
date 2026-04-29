from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Self, Iterator

from llama_cpp import Llama, ChatCompletionRequestSystemMessage, ChatCompletionRequestUserMessage, \
    ChatCompletionResponseMessage, CreateChatCompletionStreamResponse
from llama_cpp.llama_grammar import LlamaGrammar
from pydantic import ValidationError

from invoice_importer.domain.models import Invoice
from invoice_importer.interpretation.grammar import (
    grammar_from_pydantic_schema,
)
from invoice_importer.interpretation.prompts import (
    INVOICE_EXTRACTION_SYSTEM_PROMPT,
    build_user_message,
)
from invoice_importer.extraction.types import (
    ExtractedText
)
from invoice_importer.interpretation.types import LLMInterpretationError

logger = logging.getLogger(__name__)


class LlamaCppInterpreter:
    """LLM interpreter using a local GGUF model via llama-cpp-python

    Uses grammar-constrained generation to guarantee parsable JSON output
    conforming to the Invoice schema.
    """

    _model_path: str
    _n_ctx: int
    _n_gpu_layers: int
    _seed: int
    _llm: Llama | None
    _grammar: LlamaGrammar | None

    def __init__(
        self,
        *,
        model_path: str,
        n_ctx: int,
        n_gpu_layers: int,
        seed: int
    ) -> None:
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
        self._seed = seed
        self._llm = None
        self._grammar = None

    @property
    def name(self) -> str:
        return f"llama-cpp-{Path(self._model_path).stem}"


    def warmup(self) -> Self:
        """Load the model and build the grammar. Call once at startup."""
        if self._llm is not None:
            return self

        logger.info("loading local model from %s", self._model_path)
        self._llm = Llama(
            model_path=self._model_path,
            n_ctx=self._n_ctx,
            n_gpu_layers=self._n_gpu_layers,
            seed=self._seed,
            verbose=True,
        )

        logger.info("building grammar from Invoice schema")
        self._grammar = grammar_from_pydantic_schema(Invoice.model_json_schema())

        logger.info("local model ready")
        return self


    async def interpret(self, text: ExtractedText) -> Invoice:
        if self._llm is None or self._grammar is None:
            raise RuntimeError(
                "LlamaCppInterpreter.warmup() must be called before interpret()"
            )

        user_content = build_user_message(text)
        logger.info(
            "interpreting %d chars (extracted via %s) with %s",
            len(user_content),
            text.extractor,
            self.name
        )

        raw_output = await asyncio.to_thread(self._generate, user_content)

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as e:
            logger.error("model produced invalid JSON despite grammar")
            raise LLMInterpretationError(
                f"Model produced unparseable JSON: {e}"
            ) from e

        try:
            return Invoice.model_validate(data)
        except ValidationError as e:
            logger.warning(
                "LLM output failed Invoice validation: %s\nRaw output: %s",
                e,
                data
            )
            raise LLMInterpretationError(
                f"LLM produced output that failed validation: {e}"
            ) from e


    def _generate(self, user_content: str) -> str:
        """Synchronous inference call.  To be run on a worker thread via asyncio."""
        assert self._llm is not None and self._grammar is not None
        system_message: ChatCompletionRequestSystemMessage = {"role": "system", "content": INVOICE_EXTRACTION_SYSTEM_PROMPT}
        user_message: ChatCompletionRequestUserMessage = {"role": "user", "content": user_content}

        response = (
            self._llm.create_chat_completion(
                messages=[
                    system_message,
                    user_message,
                ],
                grammar=self._grammar,
                max_tokens=2048,
                temperature=0.0,
                stream=True
        ))

        choices = response["choices"]
        if not choices:
            raise LLMInterpretationError("model returned no choices")

        content = choices[0]["message"]["content"]
        if not isinstance(content, str):
            raise LLMInterpretationError(
                f"model returned non-string content: {type(content)}"
            )

        return content