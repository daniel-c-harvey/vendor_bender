# CLAUDE.md

Operational guide for Claude Code sessions in this repo. Read top-to-bottom before
making changes — most sections change *how* you should respond, not just what to know.

## Project

`invoice_importer` ingests an invoice document (PDF or image), extracts its text
preserving layout, runs an LLM to produce a validated `Invoice` matching a strict
Pydantic schema, and persists it to PostgreSQL via async SQLAlchemy.

This is also a Python learning project for a developer coming from C# / TypeScript.
Frame explanations with that lens when relevant — analogues to .NET / Node tooling
land better than abstract Python lore. The `docs/` directory holds personal study
notes, not project documentation (see § "docs/ is reference, not project docs").

## Keeping these docs current — READ FIRST

The per-layer `CLAUDE.md` files are the authoritative onboarding for future
sessions. They drift the moment code changes and the docs don't. **After any
change that touches the layer's public surface, you must update its
`CLAUDE.md` in the same change set.** "Public surface" means anything a
reader of the doc would now find wrong:

- New / renamed / removed re-exports → fix the `__init__.py` paragraph.
- Changed type names or shapes (e.g. `ExtractedText` ↔ `ExtractedDocument`)
  → fix the *What's here* bullet and any references elsewhere in the doc.
- New `.warmup()` requirement, new exception, new commit/rollback rule, new
  Protocol method → fix *Invariants*.
- Surprising behaviour you discovered the hard way → add a *Gotcha*.
- New layer, new strategy point, new extension seam → fix
  *Extension points* (and add a one-liner reference at the root level).

If a code change crosses layers, update each layer's doc. If the change
invalidates a sentence in this root file (pipeline shape, layer
responsibilities, invariants), update this file too. Doc updates ride with
the code change — don't leave them for "later".

## Toolchain & commands

- Python **3.12 only** (`requires-python = ">=3.12,<3.13"`). Pinned via `.python-version`.
- `uv` for env + locking; `hatchling` build backend; `src/`-layout package
  `src/invoice_importer/`.
- `llama-cpp-python==0.3.4` is pinned to a custom CUDA-12.4 wheel index
  (`llama-cpp-cu124` in `pyproject.toml`). Resyncing on a non-Windows / non-CUDA
  machine will fail — flag this rather than improvising a workaround.

Commands (all prefixed with `uv run`):

| Action                          | Command                                                |
|---|---|
| Run a scratch driver            | `uv run python src/scratch_importer.py`                |
| Apply migrations (real DB)      | `uv run alembic upgrade head`                          |
| Dry-run migrations (emit SQL)   | `uv run alembic upgrade head --sql`                    |
| Generate a new migration        | `uv run alembic revision --autogenerate -m "..."`      |
| Run tests                       | `uv run pytest`                                        |
| Type-check                      | `uv run pyright`                                       |
| Lint                            | `uv run ruff check .`                                  |

`tests/` holds pytest unit/integration tests against an in-memory SQLite engine
(see `tests/conftest.py`). `pytest-asyncio` is in `auto` mode — bare `async def`
test functions run without a decorator. The end-to-end development loop is still
running `src/scratch_*.py` against real PDFs / a real DB; tests cover domain,
repository, dispatcher, and importer (with faked extractor + interpreter).

`alembic` (even with `--sql`) imports `migrations/env.py`, which calls
`get_settings()` at import time. **A valid `.env` with `DATABASE_URL` *and*
`LLAMA_MODEL_PATH` is required to run alembic at all** — even though the model path
is irrelevant to migrations.

Scratch scripts assume a fixed file (e.g. `Hollow Creek Welding-2.pdf`) sits in the
current working directory. They are not generic CLIs.

## Architecture in one breath

Pipeline: `SourceContent` → `ExtractionDispatcher.extract` →
`ExtractedDocument` → `LLMInterpreter.interpret` → `Invoice` →
`repository.save_invoice` → reload via `get_invoice_by_id`.

`ExtractedDocument` is layout-preserving (pages of `TextBlock` /
`TableBlock`). `extraction/normalizer.py:TextNormalizer` flattens it into
the printable `ExtractedText` that the interpreter's prompt builder
consumes. The two types are distinct on purpose — extractors emit
structure; the prompt builder wants a string.

Layers (each non-trivial submodule has its own `CLAUDE.md` with the
layer-specific invariants — read those before touching that layer):

- `domain/` — Pydantic models + error types. Zero I/O.
  See `src/invoice_importer/domain/CLAUDE.md`.
- `extraction/` — `TextExtractor` Protocol, `ExtractionDispatcher`, layout
  clustering, and `TextNormalizer` (document → printable text). Sync,
  CPU-bound. See `src/invoice_importer/extraction/CLAUDE.md`.
- `interpretation/` — `LLMInterpreter` Protocol, Anthropic + llama-cpp clients,
  schema-derived grammar. See `src/invoice_importer/interpretation/CLAUDE.md`.
- `storage/` — async SQLAlchemy 2.0 tables, repository functions, session helpers.
  See `src/invoice_importer/storage/CLAUDE.md`.
- `orchestration/importer.py` — composes the three above into one transaction.
  See `src/invoice_importer/orchestration/CLAUDE.md`.
- `startup.py` — composition root. `build_importer()` is where wiring lives.

Dependency direction: `domain` knows nothing; `extraction` / `interpretation` /
`storage` depend on `domain`; `orchestration` depends on all of the above; `startup`
wires them. Don't introduce edges that violate this.

## Invariants — do not break

- **`domain/` has no I/O imports.** No `sqlalchemy`, no `anthropic`, no
  `pdfplumber`. If you need a domain change to satisfy a storage / LLM concern,
  the right move is almost always at the adapter layer.
- **`LLAMA_MODEL_PATH` must be absolute.** `config.py` rejects relative paths
  intentionally — do not loosen the validator.
- **`Invoice.model_json_schema()` is the LLM contract.** It is fed to Anthropic
  as a tool `input_schema` *and* to llama-cpp as a JSON-schema-derived grammar.
  Editing `Invoice` fields changes both LLMs' contract simultaneously — a
  feature, not a coincidence. Keep it that way.

Layer-specific invariants (sync-only extraction, repository-never-commits,
`expire_on_commit=False`, the two `.warmup()` requirements, etc.) live in the
respective submodule `CLAUDE.md` — read those before touching the layer.

## Conventions

- `from __future__ import annotations` at the top of every new module.
- Stdlib `logging` only; `%s` lazy formatting (`logger.info("foo %s", x)`),
  never f-strings in log calls. No `print()` outside `scratch_*.py`.
- New strategy points use `typing.Protocol`, not ABCs (see `TextExtractor`,
  `LLMInterpreter`).
- Transport types in `extraction/` are `@dataclass(frozen=True, slots=True)`;
  domain types are Pydantic `BaseModel`. Don't mix.
- Imports are absolute (`from invoice_importer.x.y import Z`), not relative.
- **Every layer is a regular package with a curated `__init__.py`** that
  re-exports its public surface — types, errors, Protocols, and lightweight
  classes (e.g. `ExtractionDispatcher`, `InvoiceImporter`). Heavy concrete
  implementations whose import pulls in large optional dependencies
  (`PdfTextExtractor` → pdfplumber, `OcrExtractor` → rapidocr,
  `AnthropicInterpreter` → anthropic, `LlamaCppInterpreter` → llama_cpp) are
  *deliberately* not re-exported and stay reachable at their deep paths.
  Internal helpers (`layout`, `prompts`, `grammar`, `tables`, `adapters`) are
  not re-exported either. New layer code follows this split.

## Database & migrations

- After changing tables: `uv run alembic revision --autogenerate -m "..."` then
  **review the generated file** before committing. Autogenerate is not
  trustworthy for type changes, server defaults, or indices on existing data.
- Schema namespace, driver split, and naming convention are documented in
  `src/invoice_importer/storage/CLAUDE.md`.

## Adding new components

- **New extractor:** see `src/invoice_importer/extraction/CLAUDE.md`.
- **New interpreter:** see `src/invoice_importer/interpretation/CLAUDE.md`.
- **New domain field:** update the Pydantic model → update the SQLAlchemy
  table → autogenerate a migration → review. Both LLM clients pick up the
  schema change automatically; no prompt edit needed unless the field needs
  human-language guidance.

## Known issues — do NOT auto-fix

See `TODO.md` at the repo root. When items are tracked there, they are tracked
deliberately. Do **not** silently fix them as drive-by cleanup in unrelated
work — surface them, leave them, and let the user decide when to address them.

## `docs/` is reference, not project docs

`docs/python-cheatsheet.md`, `docs/uv.md`, `docs/project-structure.md`,
`docs/domain/`, `docs/storage/` are **personal study notes** — generic Python /
uv / Pydantic / SQLAlchemy reference material the user wrote while learning.
They are not authoritative for *this app's* state, structure, or decisions.

When project facts disagree with `docs/`, trust the code. When asked questions
about Python / uv / Pydantic / SQLAlchemy in the abstract, the docs may be a
useful pointer.
