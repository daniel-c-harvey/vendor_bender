from pathlib import Path
from invoice_importer.extraction.extractors.ocr import OcrExtractor
from invoice_importer.extraction.types import ContentType, SourceContent


def main():
    image_path = Path("test-invoice.webp")  # any image with text
    source = SourceContent(
        data=image_path.read_bytes(),
        content_type=ContentType.PNG,
        source_identifier=str(image_path),
    )

    extractor = OcrExtractor()
    extractor.warmup()
    result = extractor.extract(source)

    print(f"Extracted via {result.extractor}")
    print(f"Pages: {result.page_count}")
    print(f"Text length: {len(result.text)} chars")
    print(f"--- text ---\n{result.text}")


if __name__ == "__main__":
    main()
