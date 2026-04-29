from pathlib import Path

from invoice_importer.extraction.extractors.ocr import OcrExtractor
from invoice_importer.extraction.types import (
    ContentType,
    SourceContent,
    TableBlock,
    TextBlock,
)


def main() -> None:
    image_path = Path("Hollow Creek Welding-2.png")
    source = SourceContent(
        data=image_path.read_bytes(),
        content_type=ContentType.PNG,
        source_identifier=str(image_path),
    )

    extractor = OcrExtractor().warmup()
    result = extractor.extract(source)

    print(f"Extracted via {result.extractor}")
    print(f"Pages: {len(result.pages)}")
    for page in result.pages:
        text_blocks = sum(1 for b in page.blocks if isinstance(b, TextBlock))
        table_blocks = sum(1 for b in page.blocks if isinstance(b, TableBlock))
        print(f"  page {page.page_number}: {text_blocks} text blocks, {table_blocks} table blocks")

    rendered = result.to_prompt()
    print(f"\n--- prompt ({len(rendered)} chars) ---\n{rendered}")


if __name__ == "__main__":
    main()
