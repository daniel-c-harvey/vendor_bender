import asyncio
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from invoice_importer.config import get_settings
from invoice_importer.domain.errors import DuplicateContentError
from invoice_importer.domain.models import Address, CurrencyCode, Invoice, InvoiceLineItem, Vendor
from invoice_importer import storage

def _create_scratch_invoice():
    return Invoice(
        invoice_number="INV-2026-001",
        issue_date=date(2026, 4, 27),
        vendor=Vendor(
            name="Test Vendor Inc",
            address=Address(
                line1="1 Main St",
                city="Anytown",
                country="US",
            ),
        ),
        currency=CurrencyCode.USD,
        line_items=(
            InvoiceLineItem(
                line_number=1,
                description="Widget",
                quantity=Decimal("2"),
                unit_price=Decimal("10.00"),
                line_total=Decimal("20.00"),
            ),
        ),
        subtotal=Decimal("20.00"),
        tax_total=Decimal("1.60"),
        grand_total=Decimal("21.60"),
    )

async def main():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    invoice = _create_scratch_invoice()
    pdf_bytes = b"fake pdf content"

    async with storage.transactional_session(factory) as session:
        row = await storage.save_invoice(
            session,
            invoice,
            source_identifier="test://example.pdf",
            content=pdf_bytes
        )
        print(f"Saved invoice id={row.id}")

    # Try to import the same content again — should raise
    try:
        async with storage.transactional_session(factory) as session:
            await storage.save_invoice(
                session,
                invoice,
                source_identifier="test://example.pdf",
                content=pdf_bytes,
            )
    except DuplicateContentError as e:
        print(f"Correctly rejected duplicate: {e}")

    await engine.dispose()


asyncio.run(main())
