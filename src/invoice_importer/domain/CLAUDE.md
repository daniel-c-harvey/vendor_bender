# domain/

Pure model layer. Pydantic schemas + error hierarchy. No I/O.

See [`../../../CLAUDE.md`](../../../CLAUDE.md) for project-wide rules.

## What's here

- `models.py` — `DomainModel` base + `Address`, `Vendor`, `InvoiceLineItem`,
  `Invoice`, plus `CurrencyCode` (StrEnum) and the `Annotated` aliases
  (`NonEmptyStr100/200/500`, `CountryCode`, `Money`, `Rate`, `Qty`).
- `errors.py` — `InvoiceImporterError` (base) and the four lookup / duplicate
  subclasses: `VendorNotFoundError`, `InvoiceNotFoundError`,
  `DuplicateInvoiceError`, `DuplicateContentError`.

No `__init__.py` (namespace package). If you add one, do it deliberately — see
the repo-hygiene item in `TODO.md`.

## Invariants

- **No I/O imports.** No `sqlalchemy`, `anthropic`, `pdfplumber`, no filesystem,
  no network. If a storage / LLM concern seems to require a domain change,
  the right move is almost always at the adapter layer.
- **Models are immutable.** `DomainModel.model_config` sets `frozen=True`,
  `extra="forbid"`, `str_strip_whitespace=True`. "Mutating" means
  `model_copy(update={...})`, never assignment. Unknown fields raise.
- **Money is `Decimal`, never `float`.** The `Money` / `Rate` / `Qty` aliases
  pin precision (`max_digits=19`, 2 or 5 decimal places). The total-consistency
  validators on `Invoice` and `InvoiceLineItem` use `Decimal('0.02')` tolerance —
  don't widen this to paper over upstream rounding bugs.
- **`Decimal` types carry `WithJsonSchema({"type": "number"})`.** This keeps
  `Invoice.model_json_schema()` LLM-friendly (Pydantic would otherwise emit
  `string` for `Decimal`). Both LLM clients consume that schema directly — see
  root *Architecture* section for why this matters.
- **Validators enforce business rules, not just shapes.** `Invoice` checks
  `due_date >= issue_date`, `subtotal == sum(line_totals)`,
  `grand_total == subtotal + tax_total`, and unique `line_number` per invoice.
  `InvoiceLineItem` checks `line_total ≈ quantity * unit_price`. Removing
  any of these silently changes what counts as a valid extracted invoice.
- **`line_items` is `tuple[..., ...]` with `min_length=1`.** Tuple, not list,
  because the model is frozen. An invoice with zero lines is invalid by
  construction.

## Extension points

Adding a domain field: edit the Pydantic model here, then update the
SQLAlchemy table in `../storage/tables.py`, then autogenerate a migration.
Both LLM clients pick up the schema change automatically — no prompt edit
needed unless the field needs human-language guidance in `interpretation/prompts/`.

Adding a new error: subclass `InvoiceImporterError`. Don't reach for
`ExtractionError` or `LLMInterpretationError` — those live in their respective
adapter layers and don't belong to the domain.

## Gotchas

- `errors.py` contains a typo ("Invoice not foud") tracked in `TODO.md`. Do
  not drive-by fix.
- `CurrencyCode` is a closed enum. Extending it is a schema change that
  flows to the DB column and the LLM contract — treat it like a domain field
  edit, not a one-line tweak.
- Pydantic's `str_strip_whitespace=True` strips on validation, so a value
  with only whitespace will fail `min_length=1` after stripping. Tests that
  pass `" "` expecting it to be accepted are wrong.
