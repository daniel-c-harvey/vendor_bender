from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from factories import make_address, make_invoice, make_line_item, make_vendor
from invoice_importer.domain.models import Invoice, CurrencyCode


def test_make_invoice_produces_valid_default():
    inv = make_invoice()
    assert inv.invoice_number == "INV-001"
    assert inv.line_items[0].line_total == Decimal("20.00")
    assert inv.subtotal == Decimal("20.00")
    assert inv.grand_total == Decimal("20.00")


def test_address_country_must_be_two_uppercase_letters():
    with pytest.raises(ValidationError):
        make_address(country="us")


def test_line_item_total_within_tolerance_accepts_small_drift():
    item = make_line_item(
        quantity=Decimal("3"),
        unit_price=Decimal("4.00"),
        line_total=Decimal("12.01"),
    )
    assert item.line_total == Decimal("12.01")


def test_line_item_total_outside_tolerance_raises():
    with pytest.raises(ValidationError):
        make_line_item(
            quantity=Decimal("3"),
            unit_price=Decimal("4.00"),
            line_total=Decimal("12.05"),
        )


def test_line_item_quantity_must_be_positive():
    with pytest.raises(ValidationError):
        make_line_item(
            quantity=Decimal("0"),
            unit_price=Decimal("10.00"),
            line_total=Decimal("0.00"),
        )


def test_invoice_subtotal_must_match_sum_of_line_totals():
    with pytest.raises(ValidationError):
        make_invoice(subtotal=Decimal("99.99"))


def test_invoice_grand_total_must_equal_subtotal_plus_tax():
    with pytest.raises(ValidationError):
        make_invoice(tax_total=Decimal("2.00"), grand_total=Decimal("100.00"))


def test_invoice_due_date_must_be_on_or_after_issue_date():
    with pytest.raises(ValidationError):
        make_invoice(
            issue_date=date(2026, 1, 15),
            due_date=date(2026, 1, 14),
        )


def test_invoice_line_numbers_must_be_unique():
    items = (
        make_line_item(line_number=1),
        make_line_item(line_number=1),
    )
    with pytest.raises(ValidationError):
        make_invoice(line_items=items)


def test_invoice_is_frozen():
    inv = make_invoice()
    with pytest.raises(ValidationError):
        inv.invoice_number = "INV-002"


def test_invoice_rejects_unknown_field():
    """DomainModel.extra='forbid' rejects fields not declared on the model."""
    with pytest.raises(ValidationError):
        Invoice(
            invoice_number="INV-1",
            issue_date=date(2026, 1, 15),
            vendor=make_vendor(),
            currency=CurrencyCode.USD,
            line_items=(make_line_item(),),
            subtotal=Decimal("20.00"),
            grand_total=Decimal("20.00"),
            unknown_field="oops",  # type: ignore[call-arg]
        )


def test_address_strips_whitespace_on_string_fields():
    """DomainModel.str_strip_whitespace=True applies to all str-typed fields."""
    addr = make_address(line1="  123 Main St  ")
    assert addr.line1 == "123 Main St"


def test_line_item_total_tolerance_pins_exact_boundary():
    """Line total tolerance is ±0.02: 0.02 drift OK, 0.03 drift not."""
    make_line_item(  # exactly at the boundary — passes
        quantity=Decimal("3"),
        unit_price=Decimal("4.00"),
        line_total=Decimal("12.02"),
    )
    with pytest.raises(ValidationError):
        make_line_item(  # one cent past the boundary — fails
            quantity=Decimal("3"),
            unit_price=Decimal("4.00"),
            line_total=Decimal("12.03"),
        )


def test_invoice_must_have_at_least_one_line_item():
    """Field(min_length=1) on line_items rejects an empty tuple."""
    with pytest.raises(ValidationError):
        make_invoice(line_items=())


def test_invoice_accepts_all_currency_codes():
    """All members of the CurrencyCode StrEnum are valid Invoice currencies."""
    for code in CurrencyCode:
        inv = make_invoice(currency=code)
        assert inv.currency == code


def test_invoice_rejects_unknown_currency_string():
    """A string that isn't a CurrencyCode member is rejected."""
    with pytest.raises(ValidationError):
        make_invoice(currency="ZZZ")


def test_line_item_line_total_rejects_excessive_decimal_places():
    """Money has decimal_places=2 — a third decimal place is invalid."""
    with pytest.raises(ValidationError):
        make_line_item(
            quantity=Decimal("1"),
            unit_price=Decimal("10.00"),
            line_total=Decimal("10.001"),
        )


def test_invoice_rejects_subtotal_mismatch_on_low_side():
    """check_totals catches subtotal-too-low as well as subtotal-too-high."""
    items = (
        make_line_item(
            line_number=1,
            quantity=Decimal("5"),
            unit_price=Decimal("10.00"),
            line_total=Decimal("50.00"),
        ),
    )
    with pytest.raises(ValidationError):
        make_invoice(line_items=items, subtotal=Decimal("40.00"))


def test_address_with_optional_fields_populated():
    """Address's optional fields (line2, region, postal_code) accept values."""
    addr = make_address(
        line1="123 Main St",
        line2="Apt 4B",
        region="CA",
        postal_code="94103",
    )
    assert addr.line2 == "Apt 4B"
    assert addr.region == "CA"
    assert addr.postal_code == "94103"