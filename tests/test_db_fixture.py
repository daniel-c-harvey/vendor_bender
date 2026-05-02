from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_importer.storage.tables import InvoiceRow, VendorRow


async def test_session_can_query_empty_tables(session: AsyncSession):
    invoices = (await session.scalars(select(InvoiceRow))).all()
    vendors = (await session.scalars(select(VendorRow))).all()
    assert invoices == []
    assert vendors == []