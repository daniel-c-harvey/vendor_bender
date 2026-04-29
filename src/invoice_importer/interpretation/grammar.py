from __future__ import annotations

import json
from typing import Any

from llama_cpp.llama_grammar import LlamaGrammar

def grammar_from_pydantic_schema(schema: dict[str, Any]) -> LlamaGrammar:
    """Convert a Pydantic-generated JSON schema into a llama.cpp grammar.

    The returned grammar can be passed to Llama.create_completion or
    Llama.__call__ via the 'grammar' parameter to constrain generation
    to outputs conforming to the schema.
    """

    schema_json = json.dumps(schema)
    return LlamaGrammar.from_json_schema(schema_json)