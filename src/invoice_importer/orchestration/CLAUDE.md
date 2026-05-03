# orchestration/

The composition layer. Wires extraction, interpretation, and storage into
one async transaction.

See [`../../../CLAUDE.md`](../../../CLAUDE.md) for project-wide rules and
the per-layer docs at [`../extraction/CLAUDE.md`](../extraction/CLAUDE.md),
[`../interpretation/CLAUDE.md`](../interpretation/CLAUDE.md), and
[`../storage/CLAUDE.md`](../storage/CLAUDE.md) for adapter-specific
invariants.

## What's here

- `importer.py` — `InvoiceImporter` with one async method,
  `import_invoice(source) -> Invoice`. Constructed once at startup with a
  dispatcher, an interpreter, and a session factory; reused per request.

No `__init__.py` (namespace package — same as `domain/`).

## Order of operations

1. **Extract** — `await asyncio.to_thread(self._dispatcher.extract, source)`.
   Extraction is sync (CPU-bound); the `to_thread` wrap is the *only*
   place async meets sync in the pipeline. Extractors must not await
   inside; this layer must not call them directly.
2. **Interpret** — `await self._interpreter.interpret(extracted)`. Async
   natively (the llama-cpp backend has its own internal `to_thread`).
3. **Persist + reload** — one `transactional_session`:
   `save_invoice(...)` then `get_invoice_by_id(invoice_row.id)`. The
   reload returns a fully hydrated domain `Invoice` with DB-generated
   fields applied; the row from `save_invoice` alone wouldn't include
   anything populated by relationship loading.

## Invariants

- **One transaction per import.** Open `transactional_session` once,
  inside it call `save_invoice` and the reload, exit. Don't split the
  save and the reload across two sessions — the reload depends on the
  save being visible, and `expire_on_commit=False` only helps within the
  same session.
- **Don't catch and swallow.** The docstring lists the four exceptions
  this method can raise (`ExtractionError`, `LLMInterpretationError`,
  `DuplicateContentError`, `DuplicateInvoiceError`). Callers catch them;
  this layer propagates.
- **No new edges.** This layer depends on `domain`, `extraction`,
  `interpretation`, `storage`. It does not depend on `startup`, and the
  three adapter layers do not depend on it. Wiring lives in `startup`.

## Gotchas

- **The reload is not free.** It's a deliberate second query so callers
  always get a domain `Invoice`, never a half-attached row. If you ever
  see this layer return an `InvoiceRow`, something has regressed.
- **Logging is `%s`-style, not f-strings** — same as everywhere else.
  The current file follows this; preserve it when adding log lines.
