
# ---------- domain -> storage ----------

from invoice_importer.domain.models import Address, CurrencyCode, Invoice, InvoiceLineItem, Vendor
from invoice_importer.storage.tables import AddressRow, InvoiceLineItemRow, InvoiceRow, VendorRow


def to_address_row(addr: Address) -> AddressRow: 
    return AddressRow(
        line1=addr.line1,
        line2=addr.line2,
        city=addr.city,
        region=addr.region,
        postal_code=addr.postal_code,
        country=addr.country,
    )

def to_vendor_row(vendor: Vendor) -> VendorRow:
    return VendorRow(
        name=vendor.name,
        tax_id=vendor.tax_id,
        address=to_address_row(vendor.address) if vendor.address else None
    )

def to_line_item_row(li: InvoiceLineItem) -> InvoiceLineItemRow:
    return InvoiceLineItemRow(
        line_number=li.line_number,
        description=li.description,
        quantity=li.quantity,
        unit_price=li.unit_price,
        line_total=li.line_total,
    )

def to_invoice_row(
    invoice: Invoice, 
    source_identifier: str, 
    content_hash: str,
    *, 
    vendor: VendorRow | None = None
) -> InvoiceRow:
    return InvoiceRow(
        invoice_number=invoice.invoice_number,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        vendor=vendor if vendor is not None else to_vendor_row(invoice.vendor),
        currency=invoice.currency,
        line_items=[to_line_item_row(li) for li in invoice.line_items],
        subtotal=invoice.subtotal,
        tax_total=invoice.tax_total,
        grand_total=invoice.grand_total,
        source_identifier=source_identifier,
        content_hash=content_hash,
    )

# ---------- storage -> domain ----------

def from_address_row(row: AddressRow) -> Address:
    return Address(
        line1=row.line1,
        line2=row.line2,
        city=row.city,
        region=row.region,
        postal_code=row.postal_code,
        country=row.country,
    )


def from_vendor_row(row: VendorRow) -> Vendor:
    return Vendor(
        name=row.name,
        tax_id=row.tax_id,
        address=from_address_row(row.address) if row.address else None,
    )


def from_line_item_row(row: InvoiceLineItemRow) -> InvoiceLineItem:
    return InvoiceLineItem(
        line_number=row.line_number,
        description=row.description,
        quantity=row.quantity,
        unit_price=row.unit_price,
        line_total=row.line_total,
    )


def from_invoice_row(row: InvoiceRow) -> Invoice:
    return Invoice(
        invoice_number=row.invoice_number,
        issue_date=row.issue_date,
        due_date=row.due_date,
        vendor=from_vendor_row(row.vendor),
        currency=CurrencyCode(row.currency),
        line_items=tuple(from_line_item_row(li) for li in row.line_items),
        subtotal=row.subtotal,
        tax_total=row.tax_total,
        grand_total=row.grand_total,
    )
