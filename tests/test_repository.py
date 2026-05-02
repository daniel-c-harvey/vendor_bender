from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_importer.domain.errors import (
    DuplicateContentError,
    DuplicateInvoiceError,
    InvoiceNotFoundError,
)
from invoice_importer.storage import repository

from factories import make_invoice, make_vendor


# ---------- get_or_create_vendor ----------

async def test_get_or_create_vendor_creates_when_not_found(session: AsyncSession):
    name = "Bepis Co"
    row = await repository.get_or_create_vendor(session, make_vendor(name=name))
    assert row.id is not None
    assert row.name == name


async def test_get_or_create_vendor_returns_existing_on_name_match(session: AsyncSession):
    name = "Bepis Co"
    first = await repository.get_or_create_vendor(session, make_vendor(name=name))
    second = await repository.get_or_create_vendor(session, make_vendor(name=name))
    assert first.id == second.id


# ---------- save_invoice ----------

async def test_save_invoice_persists_full_graph(session: AsyncSession):
    invoice = make_invoice(invoice_number="INV-A1")
    row = await repository.save_invoice(
        session,
        invoice,
        source_identifier="file://invoice-a.pdf",
        content=b"some bytes pdf"
    )
    assert row.id is not None
    assert row.invoice_number == "INV-A1"
    assert row.vendor.name == invoice.vendor.name
    assert len(row.line_items) == len(invoice.line_items)


async def test_save_invoice_raises_duplicate_content_on_same_bytes(session: AsyncSession):
    content = b"identical content"
    await repository.save_invoice(
        session, make_invoice(invoice_number="INV-B1"),
        source_identifier="x", content=content,
    )
    await session.commit()

    with pytest.raises(DuplicateContentError):
        await repository.save_invoice(
            session, make_invoice(invoice_number="INV-B2"),
            source_identifier="y", content=content,
        )


async def test_save_invoice_raises_duplicate_invoice_on_same_vendor_and_number(session: AsyncSession):
    vendor = make_vendor(name="DupCo")
    await repository.save_invoice(
        session, make_invoice(vendor=vendor, invoice_number="INV-C1"),
        source_identifier="a", content=b"contentA",
    )
    await session.commit()

    with pytest.raises(DuplicateInvoiceError):
        await repository.save_invoice(
            session, make_invoice(vendor=vendor, invoice_number="INV-C1"),
            source_identifier="b", content=b"contentB",
        )


async def test_save_invoice_reuses_existing_vendor(session: AsyncSession):
    vendor = make_vendor(name="Reused Vendor")
    row1 = await repository.save_invoice(
        session, make_invoice(vendor=vendor, invoice_number="INV-D1"),
        source_identifier="a", content=b"A",
    )
    row2 = await repository.save_invoice(
        session, make_invoice(vendor=vendor, invoice_number="INV-D2"),
        source_identifier="b", content=b"B",
    )
    assert row1.vendor_id == row2.vendor_id


# ---------- get_invoice_by_id ----------

async def test_get_invoice_by_id_returns_domain_invoice(session: AsyncSession):
    invoice = make_invoice(invoice_number="INV-E1")
    row = await repository.save_invoice(
        session, invoice, source_identifier="x", content=b"e",
    )

    fetched = await repository.get_invoice_by_id(session, row.id)
    assert fetched.invoice_number == "INV-E1"
    assert fetched.vendor.name == invoice.vendor.name
    assert len(fetched.line_items) == len(invoice.line_items)


async def test_get_invoice_by_id_raises_when_missing(session: AsyncSession):
    with pytest.raises(InvoiceNotFoundError):
        await repository.get_invoice_by_id(session, 99999)


# ---------- list_invoices_for_vendor ----------

async def test_list_invoices_for_vendor_orders_by_issue_date_desc(session: AsyncSession):
    vendor = make_vendor(name="ListCo")
    await repository.save_invoice(
        session,
        make_invoice(vendor=vendor, invoice_number="L-JAN", issue_date=date(2026, 1, 15)),
        source_identifier="a", content=b"jan",
    )
    await repository.save_invoice(
        session,
        make_invoice(vendor=vendor, invoice_number="L-FEB", issue_date=date(2026, 2, 15)),
        source_identifier="b", content=b"feb",
    )
    await repository.save_invoice(
        session,
        make_invoice(vendor=vendor, invoice_number="L-MAR", issue_date=date(2026, 3, 15)),
        source_identifier="c", content=b"mar",
    )

    results = await repository.list_invoices_for_vendor(session, "ListCo")
    assert [inv.invoice_number for inv in results] == ["L-MAR", "L-FEB", "L-JAN"]


async def test_list_invoices_for_vendor_returns_empty_when_no_match(session: AsyncSession):
    results = await repository.list_invoices_for_vendor(session, "Nonexistent")
    assert results == []