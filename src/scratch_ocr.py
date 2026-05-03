from pathlib import Path

from invoice_importer.extraction.extractors.ocr import OcrExtractor
from invoice_importer.extraction.normalizer import TextNormalizer
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
    document = extractor.extract(source)

    print(f"Extracted via {document.extractor}")
    print(f"Pages: {len(document.pages)}")
    for page in document.pages:
        text_blocks = sum(1 for b in page.blocks if isinstance(b, TextBlock))
        table_blocks = sum(1 for b in page.blocks if isinstance(b, TableBlock))
        print(f"  page {page.page_number}: {text_blocks} text blocks, {table_blocks} table blocks")

    text = TextNormalizer().normalize(document)
    print(f"\n--- prompt ({len(text.text)} chars) ---\n{text.text}")


if __name__ == "__main__":
    main()
