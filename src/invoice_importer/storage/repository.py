from __future__ import annotations
import hashlib

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from invoice_importer.storage.adapters import *
from invoice_importer.storage.tables import InvoiceRow, VendorRow
from invoice_importer.domain.models import Invoice, Vendor
from invoice_importer.domain.errors import DuplicateContentError, DuplicateInvoiceError, InvoiceNotFoundError

# ---------- Public Repo API ----------

async def get_or_create_vendor(
        session: AsyncSession,
        vendor: Vendor,
) -> VendorRow:
    """Find a vendor by name, or create a new one."""

    existing = await session.scalar(
        select(VendorRow)
        .where(VendorRow.name == vendor.name)
        .options(joinedload(VendorRow.address))
    )

    if existing is not None:
        return existing
    
    vendor_row = to_vendor_row(vendor)
    session.add(vendor_row)
    await session.flush()
    return vendor_row


async def save_invoice(
        session: AsyncSession,
        invoice: Invoice,
        *,
        source_identifier: str,
        content: bytes
) -> InvoiceRow:
    """Persist an extracted invoice. Idempotent on content hash."""

    content_hash = hashlib.sha256(content).hexdigest()

    existing = await session.scalar(
        select(InvoiceRow.id).where(InvoiceRow.content_hash == content_hash)
    )

    if existing is not None:
        raise DuplicateContentError(content_hash)
    
    vendor_row = await get_or_create_vendor(session, invoice.vendor)
    invoice_row = to_invoice_row(
        invoice, 
        source_identifier, 
        content_hash, 
        vendor=vendor_row
    )
    session.add(invoice_row)

    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise DuplicateInvoiceError(
            vendor=invoice.vendor.name,
            invoice_number=invoice.invoice_number
        ) from e
    
    return invoice_row


async def get_invoice_by_id(
    session: AsyncSession,
    invoice_id: int
) -> Invoice:
    """Load an invoice by ID, fully hydrated.  Raises if not found."""

    row = await session.scalar(
        select(InvoiceRow)
        .where(InvoiceRow.id == invoice_id)
        .options(
            joinedload(InvoiceRow.vendor)
                .joinedload(VendorRow.address),
            selectinload(InvoiceRow.line_items)
        )
    )
    if row is None:
        raise InvoiceNotFoundError(invoice_id)
    return from_invoice_row(row)


async def list_invoices_for_vendor(
    session: AsyncSession,
    vendor_name: str,
    *,
    limit: int = 100
) -> list[Invoice]:
    """List recent invoices for a vendor, most recent first."""

    rows = (await session.scalars(
        select(InvoiceRow)
        .join(VendorRow)
        .where(VendorRow.name == vendor_name)
        .order_by(InvoiceRow.issue_date.desc())
        .options(
            joinedload(InvoiceRow.vendor).joinedload(VendorRow.address),
            selectinload(InvoiceRow.line_items)
        )
    )).all()
    return [from_invoice_row(row) for row in rows]
