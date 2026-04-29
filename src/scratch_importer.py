import asyncio
import logging
from pathlib import Path

from invoice_importer.extraction.types import ContentType, SourceContent
from invoice_importer.startup import build_importer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def main():
    importer = build_importer()

    pdf_path = Path("Hollow Creek Welding-2.pdf")
    source = SourceContent(
        data=pdf_path.read_bytes(),
        content_type=ContentType.PDF,
        source_identifier=str(pdf_path),
    )

    invoice = await importer.import_invoice(source)
    print(f"\n=== Imported ===")
    print(f"Invoice: {invoice.invoice_number}")
    print(f"Vendor:  {invoice.vendor.name}")
    print(f"Total:   {invoice.grand_total} {invoice.currency.value}")
    print(f"Lines:   {len(invoice.line_items)}")


if __name__ == "__main__":
    asyncio.run(main())