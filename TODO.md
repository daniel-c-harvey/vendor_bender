# TODO

Issues surfaced during the CLAUDE.md reconnaissance pass. Triage and fix as appropriate; CLAUDE.md will warn future Claude sessions not to silently auto-fix any of these.

## Bugs

- [ ] **Prompt loader sends bytes-repr to the LLM.** `interpretation/prompts.py:11` — `_load_prompt` uses `FileIO(path)` (binary mode) and `str(file.read())`. `str(bytes_obj)` returns the repr (`"b'You are an...\\n'"`), not the decoded text. Fix: open in text mode (`Path.read_text(encoding="utf-8")`) or decode explicitly.

- [ ] **Unreachable `UnsupportedContentTypeError`.** `extraction/dispatcher.py:52-59` — dict access raises `KeyError` before the `if extractor is None` check can fire. Use `dict.get(...)` (or catch the lookup) so the friendly error actually surfaces.

- [ ] **Typo in error message.** `domain/errors.py:18` — "Invoice not foud" → "Invoice not found".

## Design smells

- [ ] **`LLMInterpretationError` inherits from `ExtractionError`.** `interpretation/types.py` — categorically wrong (an LLM failure is not an extraction failure). Callers catching `ExtractionError` will swallow interpretation failures. Move it to its own base or to `domain/errors.py`.

## Repo hygiene

- [ ] **Empty `package.json` / `package-lock.json` at repo root.** Both contain just `{}`. Either delete or replace with whatever they were intended for.

- [ ] **Inconsistent `__init__.py` presence.** `domain/`, `orchestration/`, `extraction/extractors/` have none (PEP 420 namespace packages); `extraction/`, `interpretation/`, `invoice_importer/` have empty ones. Pick one convention. Hatchling's `packages = ["src/invoice_importer"]` may or may not include namespace-only subpackages in a built wheel — worth verifying with `uv build` before publishing.
