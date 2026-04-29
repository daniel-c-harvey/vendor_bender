from pathlib import Path
from invoice_importer.extraction.extractors.pdf import PdfTextExtractor
from invoice_importer.extraction.types import ContentType, SourceContent


def main():
    pdf_path = Path("Hollow Creek Welding-2.pdf")
    source = SourceContent(
        data=pdf_path.read_bytes(),
        content_type=ContentType.PDF,
        source_identifier=str(pdf_path),
    )

    extractor = PdfTextExtractor()
    result = extractor.extract(source)
    
    print(f"Extracted via {result.extractor}")
    print(f"Pages: {result.page_count}")
    print(f"Low quality: {result.is_likely_low_quality}")
    print(f"Text length: {len(result.text)} chars")
    print(f"--- preview ---\n{result.text[:2000]}")

if __name__ == "__main__":
    main()