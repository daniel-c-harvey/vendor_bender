from pathlib import Path
from invoice_importer.extraction.dispatcher import ExtractionDispatcher
from invoice_importer.extraction.extractors.ocr import OcrExtractor
from invoice_importer.extraction.extractors.pdf import PdfTextExtractor
from invoice_importer.extraction.types import ContentType, SourceContent


def main():
    pdf_extractor = PdfTextExtractor()
    ocr_extractor = OcrExtractor().warmup()

    dispatcher = ExtractionDispatcher([pdf_extractor, ocr_extractor])
    print(f"dispatcher handles: {dispatcher.supported_content_types}")

    pdf_source = SourceContent(
        data=Path("test.pdf").read_bytes(),
        content_type=ContentType.PDF,
        source_identifier="test.pdf",
    )
    image_source = SourceContent(
        data=Path("test-invoice.webp").read_bytes(),
        content_type=ContentType.WEBP,
        source_identifier="test-invoice.webp",
    )

    pdf_result = dispatcher.extract(pdf_source)
    print(f"PDF extracted via {pdf_result.extractor}, {len(pdf_result.text)} chars")

    image_result = dispatcher.extract(image_source)
    print(f"Image extracted via {image_result.extractor}, {len(image_result.text)} chars")


if __name__ == "__main__":
    main()