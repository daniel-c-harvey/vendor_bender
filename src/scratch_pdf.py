from pathlib import Path

from invoice_importer.extraction.extractors.pdf import PdfTextExtractor
from invoice_importer.extraction.normalizer import TextNormalizer
from invoice_importer.extraction.types import (
    ContentType,
    SourceContent,
    TableBlock,
    TextBlock,
)


def main() -> None:
    pdf_path = Path("Hollow Creek Welding-2.pdf")
    source = SourceContent(
        data=pdf_path.read_bytes(),
        content_type=ContentType.PDF,
        source_identifier=str(pdf_path),
    )

    extractor = PdfTextExtractor()
    document = extractor.extract(source)

    print(f"Extracted via {document.extractor}")
    print(f"Pages: {len(document.pages)}")
    print(f"Low quality: {document.is_likely_low_quality}")
    for page in document.pages:
        text_blocks = sum(1 for b in page.blocks if isinstance(b, TextBlock))
        table_blocks = sum(1 for b in page.blocks if isinstance(b, TableBlock))
        print(f"  page {page.page_number}: {text_blocks} text blocks, {table_blocks} table blocks")

    text = TextNormalizer().normalize(document)
    print(f"\n--- prompt preview ({len(text.text)} chars) ---\n{text.text[:2000]}")


if __name__ == "__main__":
    main()
