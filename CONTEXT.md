# Invoice Importer — Context Summary for Claude Code

This is a context-loading document. Read it once at the start of a session to understand the project's history, design decisions, and current state. It complements (does not replace) `CLAUDE.md` at the repo root.

## Who is the user

Daniel Harvey, runs Cerebellum Softworks. ~20 years of software experience, primarily in C++11, C#/.NET (especially Blazor), and TypeScript. Strong background in audio production (REAPER, JUCE plugin development), live sound engineering, and systems administration (DigitalOcean, nginx, Linux). 

Hadn't written Python in 7+ years before this project started. Currently preparing for a job opportunity that involves Appian + Python AI tooling. The Invoice Importer project is a vehicle for getting back up to speed with modern Python while building something real and reusable.

He learns best by typing every character himself, connecting Python concepts to their C++/.NET/TypeScript analogues, and going step-by-step through one concept at a time. He pushes back on bad designs (with good instincts — when he objects, he's usually right).

## Project goals

1. **Re-learn Python idioms** with a focus on professional patterns: pyright-friendly type annotations, dependency injection via composition root, Protocol-based testability, async/await done right.
2. **Build a working invoice extraction system** — PDF or image in, validated structured data out, persisted to PostgreSQL.
3. **Demonstrate cost-aware LLM design** — interchangeable Anthropic and local-LLM implementations behind one Protocol, with grammar-constrained generation for the local path.
4. **Maintain reference docs** that capture the *why* of each layer, not just the what — these have been built throughout the project as `.md` files in `docs/`.

## Project architecture (high level)

```
SourceContent (bytes + content_type + identifier)
    │
    ▼
┌─────────────────────────────────────────┐
│ ExtractionDispatcher                    │
│  ├─ PdfTextExtractor (pdfplumber)       │
│  └─ OcrExtractor (rapidocr)             │
└─────────────────────────────────────────┘
    │
    ▼
ExtractedText (pages + extractor name + low-quality flag)
    │
    ▼
┌─────────────────────────────────────────┐
│ LLMInterpreter (Protocol)               │
│  ├─ AnthropicInterpreter (tool use)     │
│  └─ LlamaCppInterpreter (GBNF grammar)  │
└─────────────────────────────────────────┘
    │
    ▼
Invoice (Pydantic, validated)
    │
    ▼
┌─────────────────────────────────────────┐
│ Repository (storage layer)              │
│  ├─ get_or_create_vendor                │
│  ├─ save_invoice                        │
│  ├─ get_invoice_by_id                   │
│  └─ list_invoices_for_vendor            │
└─────────────────────────────────────────┘
    │
    ▼
Persisted Invoice (with id, imported_at, etc.)
```

The `InvoiceImporter` class in `orchestration/importer.py` ties these together inside a single transaction.

## Key design decisions and their rationale

### Pydantic for domain, SQLAlchemy for storage, hand-written adapters between

The most important architectural choice in the project. Domain models (`Invoice`, `Vendor`, etc.) are frozen Pydantic models with cross-field validation. Storage models (`InvoiceRow`, `VendorRow`) are mutable SQLAlchemy ORM classes. The `adapters.py` module has hand-written translation functions in symmetric pairs (`to_invoice_row`, `from_invoice_row`).

Rationale: shapes diverge in real projects (currency as enum vs. string, tuples vs. lists, audit fields, computed fields). Hand-written adapters expose those differences explicitly and make field changes deliberate.

The `to_invoice_row` adapter has a notable signature: `to_invoice_row(invoice, source_identifier, content_hash, *, vendor: VendorRow | None = None)`. Provenance (`source_identifier`, `content_hash`) is positional; `vendor` is keyword-only and supports the get-or-create pattern in the repository. The hash itself is computed by the caller — `repository.save_invoice` takes raw `content: bytes` and runs `hashlib.sha256` internally before passing the digest down.

### Protocols for swappable strategies

`TextExtractor` and `LLMInterpreter` are `typing.Protocol` classes. Implementations don't inherit from them — structural typing means any class with the right shape satisfies the contract. This is more Pythonic than ABCs and avoids forced inheritance hierarchies.

Pays off concretely:
- `AnthropicInterpreter` and `LlamaCppInterpreter` are completely independent classes
- The `InvoiceImporter` accepts any `LLMInterpreter` without caring which
- Test fakes can satisfy the Protocol without importing it or registering anywhere

### Grammar-constrained generation for the local LLM

The `LlamaCppInterpreter` uses llama.cpp's GBNF (Backus-Naur Form) grammar to constrain token sampling. The grammar is generated automatically from `Invoice.model_json_schema()` via `LlamaGrammar.from_json_schema()`. This *guarantees* the model produces valid JSON conforming to the schema — invalid output is impossible at the sampling layer.

Grammar enforces structure, not semantics. Pydantic validators (line totals, dates, totals consistency) still run after parsing.

### Money/Rate/Qty use `WithJsonSchema({"type": "number"})`

Pydantic's default JSON schema for `Decimal` includes an unanchored regex pattern that breaks the GBNF grammar converter. The fix is to override the JSON schema with `WithJsonSchema({"type": "number"})` in the `Annotated` chain.

This is two annotations stacked: `Field(...)` for runtime validation, `WithJsonSchema(...)` for schema generation. They're independent.

### Explicit warmup over lazy initialization

Daniel pushed back (correctly) on lazy `cached_property` initialization for `OcrExtractor`'s ML model. The current pattern: explicit `warmup()` method called by the composition root at startup. Idempotent. Failures surface at startup instead of ambushing the first user request.

`LlamaCppInterpreter.warmup()` follows the same pattern — loads the model and builds the grammar at a known time.

### Schema namespace in PostgreSQL

`Base.metadata` is configured with `schema="invoice_importer"`, putting all tables in a named PostgreSQL schema rather than `public`. This is good practice for multi-app shared databases.

Side effect: SQLite (used in tests) has no schema concept. Test fixtures will need to either strip the schema before `create_all` or test against real PostgreSQL. This is unsolved and pending for the test suite.

## Pyright-related decisions

The project uses pyright. Several patterns evolved to keep it happy:

1. **Class-level annotations for instance attributes.** Documents the class shape, lets pyright catch typos. Example:
   ```python
   class AnthropicInterpreter:
       _client: anthropic.AsyncAnthropic
       _model: str
       _max_tokens: int
       
       def __init__(self, *, api_key: str, model: str, max_tokens: int = 4096) -> None:
           self._client = anthropic.AsyncAnthropic(api_key=api_key)
           self._model = model
           self._max_tokens = max_tokens
   ```

2. **`isinstance` for type narrowing.** In the Anthropic interpreter, `isinstance(block, anthropic.types.ToolUseBlock)` narrows the block type, letting pyright accept attribute access without complaint.

3. **`TypedDict` parameter types.** The Anthropic SDK uses `ToolParam` and `ToolChoiceToolParam`. Annotating local variables with these types satisfies pyright's strict checking.

4. **Optional handling via early returns.** `if vendor is None: raise NotFoundError(...)` narrows the type for subsequent code. The pattern appears throughout the repository.

5. **`# type: ignore[call-arg]` on `Settings()`.** Pyright doesn't model pydantic-settings' env-var population, so it complains about the apparently-zero-arg call to a class with required fields. The pragma is in `config.py`'s `get_settings()`. Don't remove it without a replacement.

## What got hit and resolved during development

A non-exhaustive list of friction points encountered, for context:

- **Python 3.14 → 3.12 downgrade** because llama-cpp-python only ships Windows CUDA wheels for Python 3.12 max.
- **`pyproject.toml` build system** — initial setup didn't have `[build-system]` + `[tool.hatch.build.targets.wheel]`, so `uv sync` wasn't installing the package. Fixed by adding hatchling config.
- **`pydantic-settings` field optionality** — `database_url: str | None = None` was returning `None` silently when env was missing. Changed to required `str`.
- **`--index-url` vs. `--extra-index-url`** — `--index-url` replaces PyPI as the source; broke transitive dependency resolution. The fix is `--extra-index-url` plus `--index-strategy unsafe-best-match`, or persistent `[[tool.uv.index]]` config in pyproject.toml.
- **CUDA Toolkit installation** — `nvidia-smi` reads from the *driver*, not the toolkit. The toolkit is a separate ~3GB install that provides the runtime DLLs llama.cpp needs. Custom install (don't let it downgrade your driver).
- **Unanchored regex in GBNF converter** — the `Decimal` JSON schema fix described above.
- **Pydantic's `json_schema_extra` merges, doesn't replace** — needed to switch to `WithJsonSchema` for Decimal override.

These are all in the transcript history but listed here for quick reference if any reappear.

## Reference docs

The project has accumulated several reference docs in `docs/`:

- `docs/python/uv.md` — uv commands with npm parallels
- `docs/python/project-structure.md` — script vs. app vs. package vs. library, layouts
- `docs/domain/models.md` — Pydantic deep-dive
- `docs/storage/tables.md` — comprehensive SQLAlchemy schema reference
- `docs/storage/repository.md` — engine/session/transaction lifecycle, repository pattern, adapters

These were built deliberately as Daniel learned each piece. They're meant to be readable references, not API docs. New docs should follow the same style: thorough explanations with C#/C++/TS analogues, complete code examples, anti-patterns sections.

## What's "current" right now

End of last session (2026-04-28):

- Pipeline is end-to-end working
- Tested manually with a real PDF (Anthropic interpreter) and a hand-crafted text fixture (local interpreter)
- Local Qwen 2.5 3B with grammar produces valid output, with one observed quality issue: vendor name extraction can be slightly mangled
- All layers compose cleanly through `InvoiceImporter`
- No automated tests exist yet — that's the next planned work

Daniel was just transitioning to Claude Code from a chat session for the test-writing phase.

## What "next" looks like

Immediate next work, when Daniel comes back:

1. **Set up pytest infrastructure** — install pytest + pytest-asyncio, create `tests/` directory, add a `conftest.py`.
2. **Write a test factory module** — `make_invoice(**overrides)` and friends to reduce boilerplate in tests.
3. **Test domain validators** — Pydantic edge cases for Invoice, InvoiceLineItem.
4. **Test the repository against in-memory SQLite** — needs a fixture that handles the schema=invoice_importer issue (SQLite has no schemas). `aiosqlite` is already in `[dependency-groups] dev`, so the driver is wired up; the open question is just metadata-schema handling at fixture time.
5. **Test the dispatcher with fake extractors** — demonstrates the Protocol-based testability.
6. **End-to-end orchestrator test with all-fake dependencies** — verifies the wiring without paying real LLM costs.

Beyond tests:

- **Sources layer** — abstraction over filesystem, HTTP, email attachments. Currently the orchestrator takes raw `SourceContent`; a sources layer would produce these from various inputs.
- **CLI entry point** — argparse or click; one command to import a single file, another for a directory.
- **FastAPI application** — eventually, for service deployment.
- **Auto-fallback in dispatcher** — use `is_likely_low_quality` flag to retry pdfplumber failures with OCR.
- **Per-page PDF rasterization** for OCR fallback on scanned PDFs.

## Working style preferences

When suggesting changes:

- **Show diffs or targeted edits**, not full-file rewrites, when modifying existing code.
- **Explain the *why*** — what does this correspond to in .NET/C++/TS? What's the runtime behavior?
- **One concept per change.** Don't bundle three new patterns into one PR.
- **Connect to existing patterns in the codebase** — "same shape as OcrExtractor.warmup" beats "lazy initialization."
- **Take pushback seriously.** Daniel's instincts are good; if he objects to a design, reconsider rather than defend.
- **Don't be heavy on bullet points and headers in conversational responses** — write prose where appropriate. Reference docs and structured plans benefit from headers; explanations don't always need them.

## Pitfalls to avoid

- **Don't suggest pyright-strict mode** without checking — the codebase is pyright-friendly but not necessarily strict-clean yet. Some `# type: ignore` pragmas exist for legitimate reasons (e.g., `Settings()` call-arg complaint).
- **Don't suggest moving to ABC over Protocol.** Protocol is the deliberate choice.
- **Don't suggest dependency-injection libraries** (`dependency-injector`, `kink`, etc.). The composition-root pattern is intentional.
- **Don't suggest `SQLModel`** as a replacement for separate Pydantic + SQLAlchemy. The split is deliberate.
- **Don't migrate Python 3.12 → 3.13/3.14.** ML ecosystem wheel availability is the constraint.
- **Don't remove the `[[tool.uv.index]]` configuration** for llama-cpp-python without a replacement plan.
- **Don't change `WithJsonSchema({"type": "number"})`** on the Decimal types without testing grammar generation. It will silently break the local interpreter.

## File-level reference

Key files and what they contain (for quick navigation):

| File | Purpose |
|---|---|
| `pyproject.toml` | Dependencies, uv config, hatchling build, custom llama-cpp-python index |
| `.python-version` | Pins to 3.12 |
| `.env` (gitignored) | DATABASE_URL, ANTHROPIC_API_KEY, USE_LOCAL_LLM, LLAMA_MODEL_PATH |
| `src/invoice_importer/config.py` | Settings class, get_settings() with lru_cache |
| `src/invoice_importer/domain/models.py` | All Pydantic domain models, validators, Annotated type aliases |
| `src/invoice_importer/domain/errors.py` | Domain exception hierarchy |
| `src/invoice_importer/storage/tables.py` | All SQLAlchemy ORM classes, naming convention, schema namespace |
| `src/invoice_importer/storage/db.py` | make_engine, make_session_factory, transactional_session |
| `src/invoice_importer/storage/adapters.py` | Public to_*_row / from_*_row functions |
| `src/invoice_importer/storage/repository.py` | save_invoice, get_invoice_by_id, etc. |
| `src/invoice_importer/extraction/types.py` | SourceContent, ExtractedText, Page, TextBlock, TableBlock, ContentType enum, ExtractionError hierarchy |
| `src/invoice_importer/extraction/dispatcher.py` | ExtractionDispatcher with content-type routing |
| `src/invoice_importer/extraction/layout.py` | PositionedText, cluster_into_blocks — shared layout reconstruction used by both pdf and ocr extractors |
| `src/invoice_importer/extraction/extractors/base.py` | TextExtractor Protocol |
| `src/invoice_importer/extraction/extractors/pdf.py` | PdfTextExtractor (pdfplumber) |
| `src/invoice_importer/extraction/extractors/ocr.py` | OcrExtractor (rapidocr, explicit warmup) |
| `src/invoice_importer/interpretation/base.py` | LLMInterpreter Protocol |
| `src/invoice_importer/interpretation/types.py` | LLMInterpretationError (extends ExtractionError) |
| `src/invoice_importer/interpretation/prompts.py` | System prompt + build_user_message |
| `src/invoice_importer/interpretation/grammar.py` | grammar_from_pydantic_schema |
| `src/invoice_importer/interpretation/anthropic_client.py` | AnthropicInterpreter (tool use) |
| `src/invoice_importer/interpretation/llama_cpp_client.py` | LlamaCppInterpreter (grammar-constrained) |
| `src/invoice_importer/orchestration/importer.py` | InvoiceImporter |
| `src/invoice_importer/startup.py` | Composition root: `build_extraction()`, `build_interpreter()`, `build_session_factory()`, `build_importer()` |
| `migrations/env.py` | Alembic env, imports Base from tables, sets target_metadata |
| `migrations/versions/*.py` | Migration scripts (one initial migration applied) |
| `docs/**/*.md` | Reference notes built during development |

Scratch scripts live in `src/` (`src/scratch_*.py`) — these were used during development to test layers in isolation. They're not part of the package; they're throwaway exploratory code. New tests should not be patterned after them.
