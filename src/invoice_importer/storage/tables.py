from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, MetaData, String, Numeric, DateTime, func, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })

class AddressRow(Base):
    __tablename__ = 'addresses'
    id: Mapped[int] = mapped_column(primary_key=True)
    line1: Mapped[str] = mapped_column(String(200))
    line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(2))

    vendor: Mapped[VendorRow | None] = relationship(back_populates="address", uselist=False)

class VendorRow(Base):
    __tablename__ = 'vendors'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    tax_id: Mapped[str | None] = mapped_column(String(50))

    address_id: Mapped[int | None] = mapped_column(
        ForeignKey("addresses.id", ondelete="SET NULL"),
        unique=True
    )
    address: Mapped[AddressRow | None] = relationship(back_populates="vendor")
    invoices: Mapped[list[InvoiceRow]] = relationship(back_populates="vendor")

class InvoiceLineItemRow(Base):
    __tablename__ = 'invoice_line_items'
    __table_args__ = (
        UniqueConstraint('invoice_id', 'line_number', name='uq_invoice_line_item'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    line_number: Mapped[int]
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(19, 5))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19,5))
    line_total: Mapped[Decimal] = mapped_column(Numeric(19, 2))

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), 
        index=True
    )
    invoice: Mapped[InvoiceRow] = relationship(back_populates="line_items")

class InvoiceRow(Base):
    __tablename__ = 'invoices'
    __table_args__ = (
        UniqueConstraint('vendor_id', 'invoice_number', name='uq_vendor_invoice'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number : Mapped[str] = mapped_column(String(100))
    issue_date: Mapped[date]
    due_date: Mapped[date | None]

    vendor_id: Mapped[int] = mapped_column(
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        index=True
    )
    vendor: Mapped[VendorRow] = relationship(back_populates="invoices")

    currency: Mapped[str] = mapped_column(String(3))
    line_items: Mapped[list[InvoiceLineItemRow]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLineItemRow.line_number"
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(19, 2))
    tax_total: Mapped[Decimal] = mapped_column(Numeric(19, 2))
    grand_total: Mapped[Decimal] = mapped_column(Numeric(19, 2))

    source_identifier: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )