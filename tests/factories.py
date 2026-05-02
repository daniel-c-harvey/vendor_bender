from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from invoice_importer.domain.models import (
    Address,
    CurrencyCode,
    Invoice,
    InvoiceLineItem,
    Vendor,
)


def make_address(**overrides: Any) -> Address:
    defaults: dict[str, Any] = {
        "line1": "123 Main St",
        "city": "Springfield",
        "country": "US",
    }
    return Address(**(defaults | overrides))


def make_vendor(**overrides: Any) -> Vendor:
    defaults: dict[str, Any] = {
        "name": "Acme Corp",
    }
    return Vendor(**(defaults | overrides))


def make_line_item(**overrides: Any) -> InvoiceLineItem:
    quantity = overrides.get("quantity", Decimal("2"))
    unit_price = overrides.get("unit_price", Decimal("10.00"))
    defaults: dict[str, Any] = {
        "line_number": 1,
        "description": "Widget",
        "quantity": quantity,
        "unit_price": unit_price,
        "line_total": (quantity * unit_price).quantize(Decimal("0.01")),
    }
    return InvoiceLineItem(**(defaults | overrides))


def make_invoice(**overrides: Any) -> Invoice:
    line_items = tuple(overrides.pop("line_items", (make_line_item(),)))
    subtotal = overrides.pop(
        "subtotal",
        sum((li.line_total for li in line_items), start=Decimal("0.00")),
    )
    tax_total = overrides.pop("tax_total", Decimal("0.00"))
    grand_total = overrides.pop("grand_total", subtotal + tax_total)

    defaults: dict[str, Any] = {
        "invoice_number": "INV-001",
        "issue_date": date(2026, 1, 15),
        "vendor": make_vendor(),
        "currency": CurrencyCode.USD,
    }
    return Invoice(
        line_items=line_items,
        subtotal=subtotal,
        tax_total=tax_total,
        grand_total=grand_total,
        **(defaults | overrides),
    )