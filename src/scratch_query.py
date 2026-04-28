# scratch_query.py
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload, selectinload

from invoice_importer.config import get_settings
from invoice_importer.storage.tables import AddressRow, InvoiceRow, VendorRow


async def main():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        # insert a vendor for testing
        new_vendor = VendorRow(
            name="Acme Corp"
        )
        new_vendor.address = AddressRow(
            line1="123 Sesame Street", 
            city="Mr. Rogers' Neighborhood", 
            country="US"
        )

        session.add(new_vendor)
        await session.commit()

        # query it back
        stmt = (
            select(VendorRow)
                .where(VendorRow.name == "Acme Corp")
                .options(
                    selectinload(VendorRow.invoices)
                        .selectinload(InvoiceRow.line_items),
                    joinedload(VendorRow.address)
                )
        )
        vendor = await session.scalar(stmt)
        if vendor is None:
            raise Exception("Vendor not found: Acme Corp")
        print(f"Found: {vendor.name} with id {vendor.id}")
        if vendor.address is None:
            raise Exception("Address was not added")
        print(f"Vendor has {len(vendor.invoices)} invoices")

        # list all
        all_vendors = (await session.scalars(select(VendorRow))).all()
        print(f"Total vendors: {len(all_vendors)}")

    await engine.dispose()


asyncio.run(main())