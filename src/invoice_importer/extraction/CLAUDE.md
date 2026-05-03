# extraction/

Source bytes → layout-preserving `ExtractedText`. Sync, CPU-bound, no LLM,
no DB.

See [`../../../CLAUDE.md`](../../../CLAUDE.md) for project-wide rules.

## What's here

- `types.py` — transport types (`SourceContent`, `ExtractedText`, `Page`,
  `TextBlock`, `TableBlock`, `BBox`, `ContentType`) and the error hierarchy
  (`ExtractionError`, `UnsupportedContentTypeError`,
  `TextExtractionFailedError`). Also owns `ExtractedText.to_prompt()`, which
  renders for LLM consumption (TextBlocks pass through; TableBlocks become
  GFM tables; pages get `--- Page N ---` separators only when there are 2+).
- `extractors/base.py` — `TextExtractor` Protocol (`name`,
  `supported_content_types`, `extract`).
- `extractors/pdf.py` — `PdfTextExtractor` (pdfplumber). Detects tables
  first, clusters remaining words via `layout`, sorts merged blocks into
  reading order. Flags `is_likely_low_quality` when the largest page has
  fewer than 50 chars (likely a scanned PDF — caller may retry via OCR).
- `extractors/ocr.py` — `OcrExtractor` (rapidocr). Single-page only; no
  table detection (too hard from raw OCR bboxes). Requires `.warmup()`.
- `layout.py` — shared y-band → line → paragraph clustering. Both
  extractors normalize their fragments to `PositionedText` and call
  `cluster_into_blocks`.
- `dispatcher.py` — `ExtractionDispatcher` indexes extractors by content
  type at construction; rejects duplicate registration with `ValueError`.
- `__init__.py` — re-exports the contracts (transport types, errors,
  `TextExtractor` Protocol, `ExtractionDispatcher`). `PdfTextExtractor`
  and `OcrExtractor` are *deliberately omitted* — re-exporting them would
  force pdfplumber / rapidocr to load on any import from this layer.
  Reach them at `extraction.extractors.pdf` / `.ocr` instead.

## Invariants

- **Synchronous only.** No `async def` inside extractors. The orchestrator
  wraps the call in `asyncio.to_thread`; if you `await` here, you'll
  deadlock the event loop instead.
- **`OcrExtractor.warmup()` before `extract()`.** Loads the rapidocr model;
  guarded by a `RuntimeError` if skipped. `startup.build_extraction()` does
  this — direct construction must too.
- **Transport types are `@dataclass(frozen=True, slots=True)`, not Pydantic.**
  Keep them dumb data carriers; validation lives in `domain/`.
- **Extractors validate their own content type.** Both `PdfTextExtractor`
  and `OcrExtractor` re-check `source.content_type` and raise
  `ExtractionError` even though the dispatcher already routed by it. Don't
  drop the check — extractors get called directly in tests.
- **Empty extraction is an error, not an empty result.** Both extractors
  raise `TextExtractionFailedError` when they produce no blocks. Callers
  rely on this — don't return an empty `ExtractedText`.

## Extension points

New extractor: implement the `TextExtractor` Protocol, list it in
`startup.build_extraction()`. The dispatcher refuses to register two
extractors for the same `ContentType` — pick a new one or replace the
incumbent deliberately.

New `ContentType`: add the enum value, register an extractor for it,
update any test fixtures that enumerate supported types.

New layout strategy: `cluster_into_blocks` is the only entry point.
`y_tolerance` defaults to 30% of the median fragment height (works for
both PDF points and image pixels); `paragraph_gap_factor=0.6` is the
median-line-height multiple that splits paragraphs. Tune via kwargs
before forking the algorithm.

## Gotchas

- **`pdfplumber` table detection is good for bordered tables, less so for
  borderless ones.** Words inside a table bbox are excluded from text
  clustering by a center-point test (not corner-overlap), so a word
  grazing the border still counts as text.
- **rapidocr's output schema has changed across versions.** `_quad_to_aabb`
  silently skips entries it can't parse rather than crashing. If OCR
  results suddenly look truncated after a dependency bump, look there first.
- **`layout._Line` and `_assemble_*` are private.** Don't import them from
  extractors — they're implementation detail of `cluster_into_blocks`.
