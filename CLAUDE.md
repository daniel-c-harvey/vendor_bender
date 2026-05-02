# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project overview

**Invoice Importer** — a learning project (eventually production-shaped) that extracts structured invoice data from PDFs and images using a combination of text extraction (pdfplumber, rapidocr) and LLM interpretation (Anthropic Claude or local Qwen 2.5 via llama.cpp). Structured output is enforced via Pydantic schemas and grammar-constrained generation for the local model.

The user (Daniel) is an experienced .NET/C++/TypeScript developer (~20 years) who hadn't written Python in 7+ years before starting this. He's preparing for a job involving Appian + Python AI tooling. The project is pedagogically motivated — code quality and idiomatic patterns matter as much as functionality.

## Architecture

Strict layered architecture with clear seams. Outside `storage/`, no code imports SQLAlchemy. Outside `extraction/`, no code imports pdfplumber or rapidocr. Outside `interpretation/`, no code imports anthropic or llama-cpp.

```
src/invoice_importer/
├── config.py                          # pydantic-settings, env vars
├── domain/
│   ├── models.py                      # Pydantic domain models (Invoice, Vendor, etc.)
│   └── errors.py                      # Domain exceptions
├── storage/
│   ├── tables.py                      # SQLAlchemy ORM (*Row classes)
│   ├── db.py                          # Engine/session/transaction lifecycle
│   ├── adapters.py                    # Domain ↔ storage row translation
│   └── repository.py                  # Public storage operations
├── extraction/
│   ├── types.py                       # SourceContent, ExtractedText, Page, Block, errors
│   ├── dispatcher.py                  # Routes by content type
│   ├── layout.py                      # PositionedText, cluster_into_blocks (shared)
│   └── extractors/
│       ├── base.py                    # TextExtractor Protocol
│       ├── pdf.py                     # pdfplumber implementation
│       └── ocr.py                     # rapidocr implementation
├── interpretation/
│   ├── base.py                        # LLMInterpreter Protocol
│   ├── types.py                       # LLMInterpretationError
│   ├── prompts.py                     # System prompt + user message builder
│   ├── grammar.py                     # JSON Schema → GBNF for local model
│   ├── anthropic_client.py            # Claude implementation
│   └── llama_cpp_client.py            # Local llama.cpp implementation
├── orchestration/
│   └── importer.py                    # InvoiceImporter — end-to-end pipeline
└── startup.py                         # Composition root — build_importer()
```

Migrations: `migrations/` (Alembic, async template, autogenerate-compatible).

Reference docs: `docs/` (markdown notes documenting concepts as the project was built — uv, project structure, Pydantic, SQLAlchemy schema, repository pattern).

## Layer rules

These are non-negotiable design constraints:

1. **Domain models (Pydantic) and storage rows (SQLAlchemy) are different types.** Translate via hand-written adapters in `adapters.py`. Never `**model.model_dump()` into a row constructor.

2. **Repository functions take `AsyncSession` as a parameter.** They never create or commit sessions. The `transactional_session` context manager owns transaction boundaries; orchestrators wrap it.

3. **`expire_on_commit=False` is mandatory** on the async session factory. Default behavior would silently break attribute access in async.

4. **All eager loading is explicit.** Async SQLAlchemy disables lazy loading. Every relationship the adapter touches must be `joinedload` (scalar) or `selectinload` (collection).

5. **Domain errors at boundaries.** Translate `IntegrityError` to `DuplicateInvoiceError`/`DuplicateContentError`. Translate `ValidationError` to `LLMInterpretationError`. Don't let SQLAlchemy or anthropic exceptions cross the seam.

6. **Composition root pattern.** All wiring happens in `startup.py` (`build_importer()`). Manual constructor injection. No DI containers.

7. **Extractors are sync (CPU-bound); interpreters are async (I/O-bound or wrapped via `to_thread`).** Orchestrator uses `asyncio.to_thread` for the dispatcher call.

8. **Class-level annotations for instance attributes.** Self-documenting; pyright catches typos. Example:
   ```python
   class Foo:
       _bar: tuple[int, ...]
       _baz: dict[str, int]
       
       def __init__(self) -> None:
           self._bar = ()
           self._baz = {}
   ```

## Tooling

- **Package manager**: `uv` (not pip, not poetry). Commands: `uv add`, `uv sync`, `uv run`.
- **Python version**: 3.12 (pinned via `.python-version`). Do not "upgrade" to 3.13/3.14 — ML ecosystem wheel availability lags.
- **Type checker**: pyright. Project uses class-level annotations to keep pyright happy.
- **Linter/formatter**: ruff.
- **Migrations**: alembic (async template).
- **Database**: PostgreSQL in dev/prod (asyncpg driver), SQLite in-memory for tests (aiosqlite driver).

The `pyproject.toml` includes a custom uv index for `llama-cpp-python` (CUDA 12.4 wheel) — do not remove this, llama-cpp-python won't install correctly without it on Windows.

## Environment / settings

`.env` at project root, gitignored. Loaded by `pydantic-settings` via `Settings` in `config.py`. `model_config` uses `extra="ignore"` (not "forbid") — unknown env vars don't error.

Required (no default — `Settings()` will raise if missing, regardless of provider choice):
- `DATABASE_URL` — `postgresql+asyncpg://user:pass@host:5432/dbname`
- `LLAMA_MODEL_PATH` — path to the GGUF file (e.g. `models/Qwen2.5-3B-Instruct-Q4_K_M.gguf`)

Optional (have defaults in `config.py`):
- `USE_LOCAL_LLM` — `true` (default) routes to llama.cpp; `false` routes to Anthropic
- `ANTHROPIC_API_KEY` — `SecretStr | None` (default `None`); only consulted when `USE_LOCAL_LLM=false`. `AnthropicInterpreter` calls `.get_secret_value()` on it.
- `ANTHROPIC_MODEL` — default `claude-haiku-4-5`
- `LLAMA_N_CTX` — default `32768`
- `LLAMA_N_GPU_LAYERS` — default `-1` (all layers on GPU)
- `LLAMA_SEED` — default `0`
- `LOG_LEVEL` — default `INFO`

`get_settings()` is `@lru_cache`d — tests that need to override env must set vars *before* the first call, or clear the cache (`get_settings.cache_clear()`). The `Settings()` call carries a `# type: ignore[call-arg]` because pyright doesn't model BaseSettings env-var population.

The `models/` directory is gitignored (contains the GGUF file, ~2GB).

## Common commands

```powershell
# Install/sync dependencies
uv sync

# Run a Python script
uv run python scratch_*.py

# Database migrations
uv run alembic current                              # show current revision
uv run alembic revision --autogenerate -m "msg"     # create migration
uv run alembic upgrade head                         # apply migrations
uv run alembic downgrade -1                         # revert one

# Type checking
uv run pyright

# Linting/formatting
uv run ruff check
uv run ruff format
```

## Hardware constraints

Daniel's dev machine: laptop with **NVIDIA RTX 3050M (4GB VRAM)** and CUDA 12.5 driver. This shapes a lot of decisions:

- Local LLM is Qwen 2.5 **3B** Q4_K_M (not 7B — wouldn't fit)
- llama-cpp-python uses **prebuilt CUDA 12.4 wheels** (not built from source)
- VRAM is tight at the working configuration: `llama_n_ctx=32768` with `llama_n_gpu_layers=-1` (all layers on GPU). Treat 32K as the practical ceiling — pushing past it risks OOM. Measure before tuning.

When suggesting changes that affect inference, account for the VRAM ceiling.

## What's complete

- ✅ Domain models with cross-field validators (line totals, dates, totals consistency)
- ✅ Storage layer (tables, migrations, adapters, repository functions, transactional sessions)
- ✅ Extraction layer (PDF via pdfplumber, OCR via rapidocr, dispatcher)
- ✅ LLM interpretation (Anthropic via tool use, local via grammar-constrained generation)
- ✅ Orchestration layer (`InvoiceImporter` class composing extraction + storage)
- ✅ Composition root in `startup.py` (`build_importer()`)

## What's not yet built

- ⏳ **Tests** — no test suite exists. pytest + pytest-asyncio not yet installed. Test directory not yet created. This is the next planned work.
- ⏳ **Sources layer** — currently the orchestrator takes `SourceContent` (raw bytes). A "sources" layer would handle reading from filesystem, HTTP, email attachments, etc.
- ⏳ **Entry points** — no CLI, no FastAPI app. The orchestrator is invoked only from scratch scripts.
- ⏳ **Auto-fallback in dispatcher** — currently routes by content_type only. Eventually should fall back to OCR when pdfplumber returns low-quality text (the `is_likely_low_quality` flag is set but unused).
- ⏳ **Per-page PDF→image conversion** — for scanned PDFs that need OCR.

## Code style preferences

- **Concise but not cryptic.** Daniel prefers explicit code that reads naturally.
- **Type annotations everywhere.** Including return types on every function. Including class-level annotations for instance attributes.
- **`from __future__ import annotations`** at the top of every module. Project standard.
- **Specific exception types.** Never raise `Exception(...)` directly; use a typed subclass (often a domain error).
- **Keyword-only arguments after `*`** for any boolean or "config-like" parameter. Position-only is fine for the primary subject of an operation.
- **Hand-written translations and explicit construction.** Avoid magic. The composition root style is the project's central idiom.
- **Small files, clear boundaries.** A module with one purpose is preferred over a god-module with everything.

## Pedagogical notes

Daniel learns by typing every character himself — he has not used copy-paste-style code generation during development. When proposing edits, prefer:

1. **Explanations of the *why* alongside the *what*.** What does this concept correspond to in C++/.NET/TypeScript? What does the runtime do?
2. **Showing diffs or specific edits**, not entire file rewrites, when changing existing code.
3. **One concept at a time.** Don't introduce three new patterns in a single change.
4. **Connect to existing patterns in the codebase.** "Same shape as the OcrExtractor's warmup" lands better than "use the lazy-init pattern."

He pushes back on bad designs (he correctly objected to lazy initialization in OcrExtractor and demanded explicit warmup). Take pushback seriously — he's usually right.

## Domain model reference

For convenience, the core types:

```python
class Address(DomainModel):
    line1: NonEmptyStr200
    line2: str | None = None
    city: NonEmptyStr100
    region: str | None = None
    postal_code: str | None = None
    country: CountryCode  # ISO 3166-1 alpha-2

class Vendor(DomainModel):
    name: NonEmptyStr200
    address: Address | None = None
    tax_id: str | None = None

class InvoiceLineItem(DomainModel):
    line_number: int       # > 0, unique within invoice
    description: NonEmptyStr500
    quantity: Qty           # Decimal(19,5), > 0
    unit_price: Rate        # Decimal(19,5)
    line_total: Money       # Decimal(19,2), validates qty*price within 0.02

class Invoice(DomainModel):
    invoice_number: NonEmptyStr100
    issue_date: date
    due_date: date | None = None      # >= issue_date if present
    vendor: Vendor
    currency: CurrencyCode             # USD/EUR/GBP/CAD/AUD/JPY
    line_items: tuple[InvoiceLineItem, ...]   # min_length=1
    subtotal: Money         # validates sum of line_totals within 0.02
    tax_total: Money = Decimal("0.00")
    grand_total: Money      # validates subtotal + tax_total within 0.02
```

`DomainModel` is `BaseModel` with `frozen=True`, `extra="forbid"`, `str_strip_whitespace=True`.

`Money`, `Rate`, `Qty` are `Annotated[Decimal, Field(...), WithJsonSchema({"type": "number"})]` — the `WithJsonSchema` is critical, it makes the LLM-facing JSON schema use `"type": "number"` instead of Pydantic's default unanchored-regex string type, which breaks GBNF grammar generation.

## When in doubt

- Read the relevant doc in `docs/` before making structural changes (especially `docs/storage/tables.md` and `docs/storage/repository.md`).
- Check `pyproject.toml` for the canonical dependency list.
- Run `uv run alembic current` to confirm DB state before generating migrations.
- For new code, follow the patterns in existing layers — they were chosen deliberately.
