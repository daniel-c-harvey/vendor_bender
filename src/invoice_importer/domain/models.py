from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self
from pydantic import BaseModel, Field, ConfigDict, model_validator, WithJsonSchema

NonEmptyStr100 = Annotated[str, Field(min_length=1, max_length=100)]
NonEmptyStr200 = Annotated[str, Field(min_length=1, max_length=200)]
NonEmptyStr500 = Annotated[str, Field(min_length=1, max_length=500)]
CountryCode = Annotated[str, Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")]
Money = Annotated[Decimal, Field(max_digits=19, decimal_places=2), WithJsonSchema({"type": "number"})]
Rate = Annotated[Decimal, Field(max_digits=19, decimal_places=5), WithJsonSchema({"type": "number"})]
Qty = Annotated[Decimal, Field(max_digits=19, decimal_places=5, gt=0), WithJsonSchema({"type": "number"})]

class CurrencyCode(StrEnum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    CAD = "CAD"
    AUD = "AUD"
    JPY = "JPY"


class DomainModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True
    )

class Address(DomainModel):
    line1: NonEmptyStr200
    line2: str | None = Field(default=None, max_length=200)
    city: NonEmptyStr100
    region: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: CountryCode

class Vendor(DomainModel):
    name: NonEmptyStr200
    address: Address | None = None
    tax_id: str | None = Field(default=None, max_length=50)

class InvoiceLineItem(DomainModel):
    line_number: int = Field(gt=0)
    description: NonEmptyStr500
    quantity: Qty
    unit_price: Rate
    line_total: Money

    @model_validator(mode='after')
    def check_line_total(self) -> Self:
        expected = (self.quantity * self.unit_price).quantize(Decimal('0.01'))
        if abs(self.line_total - expected) > Decimal('0.02'):
            raise ValueError(
                f"line_total {self.line_total} is inconsistent with expected {expected}"
            )
        return self
    
class Invoice(DomainModel):
    invoice_number: NonEmptyStr100
    issue_date: date
    due_date: date | None = None
    vendor: Vendor
    currency: CurrencyCode
    line_items: tuple[InvoiceLineItem, ...] = Field(min_length=1)
    subtotal: Money
    tax_total: Money = Field(default=Decimal('0.00'))
    grand_total: Money

    @model_validator(mode='after')
    def check_dates(self) -> Self:
        if self.due_date is not None and self.due_date < self.issue_date:
            raise ValueError(
                f"due_date {self.due_date} must be on or after "
                f"issue_date {self.issue_date}"
            )
        return self

    @model_validator(mode='after')
    def check_totals(self) -> Self:
        line_sum = sum(
            (li.line_total for li in self.line_items),
            start=Decimal('0.00')
        )
        if abs(self.subtotal - line_sum) > Decimal('0.02'):
            raise ValueError(
                f"subtotal {self.subtotal} is inconsistent "
                f"with expected line items total {line_sum}"
            )
        expected_grand = self.subtotal + self.tax_total
        if abs(self.grand_total - expected_grand) > Decimal('0.02'):
            raise ValueError(
                f"grand_total {self.grand_total} is inconsistent "
                f"with expected grand total {expected_grand}"
            )
        return self
    
    @model_validator(mode='after')
    def check_line_numbers_unique(self) -> Self:
        numbers = [li.line_number for li in self.line_items]
        if len(numbers) != len(set(numbers)):
            raise ValueError("line_numbers must be unique within an invoice")
        return self
