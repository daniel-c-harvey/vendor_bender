# interpretation/

`ExtractedText` → validated `Invoice`, via an LLM. Async at the interface;
the local backend hides a sync inference call behind `asyncio.to_thread`.

See [`../../../CLAUDE.md`](../../../CLAUDE.md) for project-wide rules.

## What's here

- `base.py` — `LLMInterpreter` Protocol (`name`, async `interpret`).
- `anthropic_client.py` — `AnthropicInterpreter`. Forces a single
  `tool_use` call to a `record_invoice` tool whose `input_schema` is
  `Invoice.model_json_schema()`. The tool's `input` dict goes straight to
  `Invoice.model_validate`.
- `llama_cpp_client.py` — `LlamaCppInterpreter`. Local GGUF via
  `llama-cpp-python`, with grammar-constrained generation derived from the
  same schema, so the model can only emit conforming JSON.
- `grammar.py` — one function: `grammar_from_pydantic_schema` →
  `LlamaGrammar.from_json_schema`. The schema-to-grammar bridge.
- `prompts.py` — loads `prompts/invoice_extraction_system_prompt.txt` and
  builds the user message (`<invoice_document>...</invoice_document>` +
  tool instruction).
- `prompts/invoice_extraction_system_prompt.txt` — the system prompt.
  Edit-as-text; not tracked separately as code.
- `types.py` — `LLMInterpretationError`.
- `__init__.py` — re-exports the contracts (`LLMInterpreter` Protocol,
  `LLMInterpretationError`). `AnthropicInterpreter` and `LlamaCppInterpreter`
  are *deliberately omitted* — re-exporting them would force anthropic /
  llama_cpp to load on any import from this layer. Reach them at
  `interpretation.anthropic_client` / `.llama_cpp_client` instead.

## Invariants

- **`Invoice.model_json_schema()` is the LLM contract.** Both clients
  consume it — Anthropic as `tool.input_schema`, llama-cpp as a grammar.
  Editing `Invoice` in `domain/` retunes both backends in lockstep. Don't
  hand-author a parallel schema here.
- **`LlamaCppInterpreter.warmup()` before `interpret()`.** Loads the GGUF
  and builds the grammar; both are required and a `RuntimeError` fires if
  skipped. `startup.build_interpreter()` does this — direct construction
  must too.
- **Interpreters are async at the boundary.** The Anthropic client awaits
  the SDK natively; the llama-cpp client wraps `_generate` in
  `asyncio.to_thread` because llama-cpp is synchronous. Don't call
  `Llama.create_chat_completion` directly from the async path.
- **Validation is non-negotiable.** Every backend ends with
  `Invoice.model_validate`; a parse that returns `dict` but doesn't
  validate is `LLMInterpretationError`, not a partial Invoice.

## Extension points

New interpreter: implement the `LLMInterpreter` Protocol, branch on a
`Settings` flag in `startup.build_interpreter()`. Reuse
`build_user_message` and `INVOICE_EXTRACTION_SYSTEM_PROMPT` so all
backends see the same prompt surface.

If you need a different system prompt per backend, add another `.txt`
under `prompts/` and load it via `_load_prompt`.

## Gotchas

- **The llama-cpp call is `stream=True` but the code reads
  `response["choices"]` as if it were a non-streamed dict.** It works
  because llama-cpp-python accumulates and returns a final dict in
  practice, but the `Iterator`/`CreateChatCompletionStreamResponse` import
  hints suggest the original intent was different. If you change
  generation parameters, verify the response shape rather than trusting
  the type hint.
- **Anthropic API errors are caught broadly as `anthropic.APIError`.**
  Auth, rate-limit, and overload all collapse into one
  `LLMInterpretationError`. Distinguish at the call site if you need to.
