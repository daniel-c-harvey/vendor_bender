# extraction/

Source bytes → layout-preserving `ExtractedDocument`, then optionally
flattened to `ExtractedText` for prompt assembly. Sync, CPU-bound, no LLM,
no DB.

See [`../../../CLAUDE.md`](../../../CLAUDE.md) for project-wide rules.

## What's here

- `types.py` — transport types and the error hierarchy.
  - **Inputs:** `SourceContent`, `ContentType`.
  - **Layout primitives:** `BBox`, `TextBlock`, `TableBlock`, the
    `Block = TextBlock | TableBlock` union, and `Page` (page number +
    blocks in reading order).
  - **Outputs:** `ExtractedDocument` (rich, layout-preserving — pages of
    blocks plus extractor name and `is_likely_low_quality` flag) and
    `ExtractedText` (flat printable string used by the interpreter's
    prompt builder, plus the same provenance fields).
  - **Errors:** `ExtractionError`, `UnsupportedContentTypeError`,
    `TextExtractionFailedError`.
- `normalizer.py` — `TextNormalizer.normalize(document) -> ExtractedText`.
  TextBlocks pass through; TableBlocks become GitHub-flavored Markdown
  tables (`|` escaped, embedded newlines collapsed to spaces, short rows
  padded); blocks within a page join on blank lines; multi-page documents
  get `--- Page N ---` separators (single-page documents stay clean).
  This is the *only* place document → string flattening lives — neither
  `ExtractedDocument` nor `ExtractedText` carries a render method.
- `extractors/base.py` — `TextExtractor` Protocol (`name`,
  `supported_content_types`, `extract(source) -> ExtractedDocument`).
- `extractors/pdf.py` — `PdfTextExtractor` (pdfplumber) → `ExtractedDocument`.
  Detects tables first, clusters remaining words via `layout`, sorts merged
  blocks into reading order per page. Flags `is_likely_low_quality` when
  the largest page has fewer than 50 chars (likely a scanned PDF — caller
  may retry via OCR).
- `extractors/ocr.py` — `OcrExtractor` (rapidocr) → single-page
  `ExtractedDocument`. No table detection (too hard from raw OCR bboxes).
  Requires `.warmup()`.
- `layout.py` — shared y-band → line → paragraph clustering. Both
  extractors normalize their fragments to `PositionedText` and call
  `cluster_into_blocks` to produce `TextBlock`s.
- `dispatcher.py` — `ExtractionDispatcher` indexes extractors by content
  type at construction; rejects duplicate registration with `ValueError`.
  `extract(source) -> ExtractedDocument`.
- `__init__.py` — re-exports the public surface: transport types
  (`SourceContent`, `ContentType`, `BBox`, `TextBlock`, `TableBlock`,
  `Block`, `Page`, `ExtractedDocument`, `ExtractedText`), errors,
  `TextExtractor` Protocol, `ExtractionDispatcher`, and `TextNormalizer`.
  `PdfTextExtractor` and `OcrExtractor` are *deliberately omitted* —
  re-exporting them would force pdfplumber / rapidocr to load on any
  import from this layer. Reach them at `extraction.extractors.pdf` /
  `.ocr` instead.

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
  rely on this — don't return an empty `ExtractedDocument`.
- **`ExtractedDocument` carries structure; `ExtractedText` carries a
  flat string.** Don't add a `.text` property to `ExtractedDocument` or a
  `.pages` property to `ExtractedText`; the split is the whole point of
  having a `TextNormalizer`. If a consumer needs both shapes, hold the
  document and normalize on demand.

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
