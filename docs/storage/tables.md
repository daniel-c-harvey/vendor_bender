# SQLAlchemy & Storage Layer — Reference Notes

## 1. What SQLAlchemy is

A two-layer Python ORM and SQL toolkit.

**SQLAlchemy Core** — a programmatic SQL expression language. You construct Python objects (`select()`, `insert()`, columns, tables) that compile to SQL strings and execute against a database. No object identity, no change tracking.

**SQLAlchemy ORM** — built on top of Core. Maps Python classes to tables; a `Session` tracks loaded objects and pending changes, syncing them to the database on commit.

You'll mostly use the ORM. Drop to Core occasionally for bulk operations where ORM overhead matters.

Conceptually parallel to EF Core in .NET, but more philosophically explicit about lifecycle and unit-of-work boundaries.

## 2. Engine vs. Session

Two distinct objects with distinct lifecycles. Coming from EF Core: don't conflate `DbContext` with both — they map to *different* SQLAlchemy concepts.

**The `AsyncEngine`** is the long-lived connection pool plus dialect. Created once per application at startup. Knows how to talk to the DB (driver, URL, pool size). Not transactional; not tied to a request.

```python
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@host/dbname",
    echo=False,
    pool_pre_ping=True,
)
```

Closest .NET parallel: `DbContextOptions` + the connection pool combined.

**The `AsyncSession`** is the short-lived unit of work. Created per logical operation (per request, per batch, per test). Holds a connection, tracks loaded objects, tracks pending changes, flushes them as SQL on commit.

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

session_factory = async_sessionmaker(engine, expire_on_commit=False)

async with session_factory() as session:
    # work happens here
    await session.commit()
```

Closest .NET parallel: `DbContext` itself.

The hard rule: **one session per logical operation, created fresh, disposed at end.** Never long-lived, never shared across requests.

### `expire_on_commit=False`

Mandatory for async sessions. The default (`True`) expires loaded attributes after commit, causing the next attribute access to refetch from the DB. Sync code can hide this; async code can't — implicit reload would need to await, which attribute access can't do, so it crashes. Always `expire_on_commit=False` for async.

## 3. Connection URLs

```
postgresql+asyncpg://user:pass@host:5432/dbname
sqlite+aiosqlite:///:memory:
sqlite+aiosqlite:///./local.db
```

The `+driver` part specifies the driver. Async drivers go with `create_async_engine`; sync drivers with `create_engine`. Mismatching them silently fails in confusing ways.

For this project:
- **Production:** `postgresql+asyncpg://...` (asyncpg installed via `uv add asyncpg`)
- **Tests:** `sqlite+aiosqlite:///:memory:` (aiosqlite installed via `uv add --dev aiosqlite`)

## 4. Transactions

Sessions use **autobegin**: the first query or flush implicitly begins a transaction. End it explicitly:

```python
await session.commit()    # commit the transaction
await session.rollback()  # discard pending changes
```

After commit/rollback, the session is still usable; the next operation begins a new transaction.

For block-scoped transactions:

```python
async with session.begin():
    session.add(thing)
    # commit on successful exit; rollback on exception
```

For session creation + transaction management combined into one expression, use a custom context manager:

```python
@asynccontextmanager
async def transactional_session(factory):
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

Pattern: **the caller owns the transaction.** Repository functions don't commit; they add/query/modify. The orchestrating code (route handler, CLI command, batch job) wraps a set of repository calls in `transactional_session` to define the boundary.

## 5. Async lazy-loading is disabled

In sync SQLAlchemy, accessing `invoice.vendor` can silently trigger a DB query. In async, that can't work — `__getattribute__` can't be `await`ed. So async SQLAlchemy disables lazy loading by default.

Three options for relationship access in async:
- **Eager-load up front:** `select(InvoiceRow).options(selectinload(InvoiceRow.vendor))`
- **Explicitly refresh:** `await session.refresh(obj, ["vendor"])`
- **Configure the relationship for async-friendly loading:** add `lazy="selectin"` or similar at the class level

The forced explicitness is a feature: it eliminates N+1 query bugs by construction.

## 6. Declarative tables

Modern SQLAlchemy 2.0 uses type-annotated class bodies, same metaclass-driven pattern as Pydantic.

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class VendorRow(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
```

What happens at class creation time:
- The metaclass walks `__annotations__`, reads `mapped_column(...)` calls.
- Builds a parallel `Table` object on `Base.metadata`.
- Replaces class attributes with `InstrumentedAttribute` descriptors that intercept get/set.
- Configures the mapper linking the class to the table.

By the time the class statement finishes, `VendorRow.__table__` exists, columns are registered, and class attributes serve double duty: query expressions on the class, real values on instances.

### Annotation-driven inference

SQLAlchemy reads the `Mapped[T]` annotation for several things:

| From annotation | Inferred |
|---|---|
| `Mapped[int]` | `INTEGER NOT NULL` |
| `Mapped[str]` | needs `String(N)` for length |
| `Mapped[str \| None]` | nullable |
| `Mapped[Decimal]` | needs `Numeric(p, s)` for precision |
| `Mapped[date]` | `DATE NOT NULL` |
| `Mapped[datetime]` | needs `DateTime(timezone=True)` for tz-aware |

Bare types (int, bool, date, datetime) often need no `mapped_column(...)` if no extra config is required:

```python
issue_date: Mapped[date]
due_date: Mapped[date | None]
```

`str` and `Decimal` essentially always need `mapped_column(String(N))` / `mapped_column(Numeric(p, s))` for type precision.

### Common column types

```python
String(N)            # VARCHAR(N)
Text                 # unbounded text
Integer              # INTEGER (auto-inferred from Mapped[int])
BigInteger           # 64-bit integer
Boolean              # auto-inferred from Mapped[bool]
Numeric(p, s)        # NUMERIC(p, s) — exact decimal
Date                 # auto-inferred from Mapped[date]
DateTime(timezone=True)  # TIMESTAMPTZ on PG
LargeBinary          # BLOB / bytea
JSON / JSONB         # JSONB on PG (preferred for indexing)
Uuid                 # native UUID on PG
```

Two rules that matter:
- **Always specify `String(N)` length** — without it you get `TEXT` on PG, `VARCHAR` without limit elsewhere. Match your Pydantic constraints.
- **Always `DateTime(timezone=True)`** — naive timestamps are a recurring bug source. PG stores as `TIMESTAMPTZ`.

### Server-generated defaults

```python
imported_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
)
```

`server_default` generates `DEFAULT now()` in DDL; the database fills the value on insert. Distinct from `default=`, which runs Python code at insert time.

`func.now()` is dialect-portable. It generates `now()` on PG and `CURRENT_TIMESTAMP` on SQLite. Always prefer `func.now()` over Python's `datetime.now()` for audit timestamps — DB clock is authoritative.

For audit fields that update on every change, add `onupdate=func.now()`.

## 7. Foreign keys and `ON DELETE`

```python
vendor_id: Mapped[int] = mapped_column(
    ForeignKey("vendors.id", ondelete="RESTRICT"),
    index=True,
)
```

- `"vendors.id"` — string reference to table.column, resolved lazily so class definition order doesn't matter.
- `ondelete=` — emits the SQL `ON DELETE` clause:
  - `"CASCADE"` — child rows deleted when parent is deleted (use for owned children).
  - `"RESTRICT"` — delete fails if children exist (use for shared/historical references).
  - `"SET NULL"` — child FK set to NULL (column must be nullable).
  - `"NO ACTION"` — DB default; usually equivalent to RESTRICT.
- `index=True` — creates an index on the FK column (joins on unindexed FKs are slow; almost always wanted).

Naming convention: prefix with `fk_` for clarity in migrations. Configurable via the `MetaData(naming_convention=...)` setting.

`onupdate=` exists too, for natural keys that mutate. For auto-increment integer PKs, leave it out — they don't change.

## 8. Relationships

Foreign key columns describe storage; `relationship()` describes navigation.

```python
class VendorRow(Base):
    invoices: Mapped[list[InvoiceRow]] = relationship(back_populates="vendor")

class InvoiceRow(Base):
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    vendor: Mapped[VendorRow] = relationship(back_populates="invoices")
```

Annotations encode cardinality:
- `Mapped[Other]` — to-one
- `Mapped[Other | None]` — optional to-one
- `Mapped[list[Other]]` — to-many

Both sides must declare the relationship and reference each other by attribute name in `back_populates`. SQLAlchemy refuses to guess the pairing.

### `uselist=False` for one-to-one

When a foreign key has `unique=True`, the relationship becomes physically 1:1. The reverse-side annotation needs `uselist=False` to override SQLAlchemy's default "reverse of FK = collection":

```python
class AddressRow(Base):
    vendor: Mapped[VendorRow | None] = relationship(
        back_populates="address",
        uselist=False,
    )

class VendorRow(Base):
    address_id: Mapped[int | None] = mapped_column(
        ForeignKey("addresses.id", ondelete="SET NULL"),
        unique=True,    # enforces 1:1 at the DB level
    )
    address: Mapped[AddressRow | None] = relationship(back_populates="vendor")
```

Why explicit? The annotation alone is ambiguous — `Mapped[Other]` looks identical for many-to-one and one-to-one. Only `unique=True` on the FK column physically distinguishes them, and `uselist=False` tells the ORM to reflect that at the Python level. SQLAlchemy refuses to infer 1:1 from the annotation alone because if the `unique` constraint were missing, the data could violate the inferred semantics.

### Cascade for owned children

```python
line_items: Mapped[list[LineItemRow]] = relationship(
    back_populates="invoice",
    cascade="all, delete-orphan",
    order_by="LineItemRow.line_number",
)
```

Two layers cooperate:

**ORM-level cascade** (`cascade="all, delete-orphan"`):
- `"all"` includes save-update, merge, refresh-expire, expunge, delete.
- `"delete-orphan"` — if a child is removed from the collection, delete the row.

**DB-level cascade** (`ondelete="CASCADE"` on the FK):
- DB enforces deletion cascading even for non-ORM operations (raw SQL, bulk deletes, other apps).

Use both for owned children. The ORM cascade handles deletions through the session; the DB cascade handles everything else.

`order_by="ChildClass.field"` — provides a default sort for the collection. Without it, row order is unspecified.

## 9. Composite constraints — `__table_args__`

Multi-column constraints go in a tuple at the class level:

```python
class InvoiceRow(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("vendor_id", "invoice_number", name="uq_vendor_invoice"),
    )
```

Three Python-specific points:

**Must be a tuple.** Trailing comma required for single-element: `(UniqueConstraint(...),)`. Without it, Python sees `(UniqueConstraint(...))` as just a parenthesized expression, not a tuple.

**Always name constraints.** Without `name=`, you get auto-generated names that vary by dialect and break Alembic autogenerate. Convention:
- `uq_` for unique
- `ck_` for check
- `ix_` for index
- `fk_` for foreign key
- `pk_` for primary key

**Single-column constraints stay on `mapped_column`.** Reach for `__table_args__` only when the constraint spans multiple columns.

Other things that go in `__table_args__`:
```python
CheckConstraint("grand_total >= 0", name="ck_grand_total_nonneg")
Index("ix_invoice_issue_date", "issue_date")
Index("ix_invoice_composite", "vendor_id", "issue_date")
```

A trailing dict is allowed for table options:
```python
__table_args__ = (
    UniqueConstraint(...),
    {"schema": "accounting"},
)
```

## 10. Forward references and `from __future__ import annotations`

Class bodies execute top to bottom. References to classes defined later in the file fail at definition time:

```python
class VendorRow(Base):
    invoices: Mapped[list[InvoiceRow]] = relationship(...)  # NameError

class InvoiceRow(Base):
    ...
```

Two fixes:

**String forward reference** for one-off cases:
```python
invoices: Mapped[list["InvoiceRow"]] = relationship(...)
```

**`from __future__ import annotations` at the top of the file** for module-wide lazy evaluation:
```python
from __future__ import annotations
# now all annotations are strings, evaluated only on demand
class VendorRow(Base):
    invoices: Mapped[list[InvoiceRow]] = relationship(...)  # works
class InvoiceRow(Base):
    ...
```

Always use the future import. Modern Pydantic, SQLAlchemy, FastAPI all handle PEP 563 lazy annotations correctly.

The string-based references in `relationship()` arguments (`order_by="LineItemRow.line_number"`, FK `"invoices.id"`) are SQLAlchemy's own deferred-resolution mechanism — separate from Python's, but motivated by the same need.

## 11. Domain ↔ storage separation

Two different types for the same concept:

- **Domain model** (Pydantic): `Invoice`, `LineItem`, `Vendor`. Frozen, validated, immutable, no I/O dependencies. Represents *what an invoice is*.
- **Storage model** (SQLAlchemy): `InvoiceRow`, `LineItemRow`, `VendorRow`. Mutable instrumented objects tied to DB rows. Represents *how invoice data is stored*.

The repository layer translates between them via dedicated adapter functions (see `repository.md`). Why bother?

1. **Domain stays free of ORM concerns.** No SQLAlchemy in your business logic.
2. **Storage stays free of domain validation.** Loading a row doesn't re-run cross-field invariants.
3. **The shapes can diverge.** Storage might have audit fields, soft-delete flags, denormalized columns the domain doesn't care about. Domain might have computed fields the storage doesn't persist.
4. **Different lifecycle requirements.** Domain models are immutable values; storage models are mutable identity-tracked entities.

Naming convention: `*Row` suffix on storage models disambiguates clearly. (Other conventions: `*Entity`, `*Model`, separate namespaces.)

### Domain models don't need bidirectional relationships

The ORM requires both sides for change tracking and graph consistency. Domain models don't:

```python
class Vendor(DomainModel):
    name: str
    address: Address | None
    # NO `invoices` field
```

When does `Invoice` need a reference to `Vendor`? Always — every invoice has one vendor.
When does `Vendor` need a reference to all invoices? Almost never — that's a different aggregate, a different read path, a different use case.

If a separate workflow legitimately needs "vendor with all invoices," create a *different* model for it (`VendorWithHistory`, etc.) rather than bolting the relationship onto the importer's `Vendor`. One class, one purpose.

## 12. Database creation strategies

**Tests:** use `Base.metadata.create_all` against in-memory SQLite. Fast, fresh per test, no migration overhead.

```python
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

`engine.begin()` opens a transaction; `run_sync` runs a sync function (DDL operations are sync) on a wrapped sync view of the async connection. Greenlet-based bridging.

**Production / shared environments:** use Alembic migrations. Never `create_all`.

**Local dev DB:** use migrations. Catches "I forgot to write a migration."

## 13. Naming convention for metadata

Add this to `Base` early — Alembic autogenerate works much better with deterministic constraint names:

```python
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
        schema="invoice_importer",
    )
```

Without this, PG and SQLite generate different default names and Alembic gets confused reconciling them. Set it before the first migration; changing the convention later requires a coordinated rename effort.

The `schema=` argument places all tables in a named PostgreSQL schema (rather than the default `public`). Useful for namespacing in shared databases — multiple apps can coexist in one DB, each in their own schema. Tests against SQLite generally need to either drop the schema or use a workaround, since SQLite has no schema concept.

## 14. Design checklist for a storage table

1. **`__tablename__`** — explicit; conventional plural snake_case.
2. **Primary key** — `id: Mapped[int] = mapped_column(primary_key=True)` for synthetic PKs.
3. **Match domain nullability.** If the domain model says `Optional[X]`, the column should be nullable. Drift causes runtime bugs.
4. **Match domain precision.** `Numeric(p, s)` should mirror Pydantic's `max_digits` / `decimal_places`.
5. **Index foreign keys.** Joins on unindexed FKs are slow.
6. **Specify `ondelete`** on every foreign key. Don't rely on DB defaults.
7. **Cascade owned children.** `cascade="all, delete-orphan"` on the relationship + `ondelete="CASCADE"` on the FK.
8. **Name constraints.** Always provide `name=` to `UniqueConstraint`, `CheckConstraint`, `Index`.
9. **Add audit fields where appropriate.** `imported_at` (immutable record) or `created_at` + `updated_at` (mutable record).
10. **Provenance for imported data.** `source_identifier` and a content hash for idempotency.

## 15. Useful patterns

### Idempotency via content hash

```python
content_hash: Mapped[str] = mapped_column(String(64), unique=True)
```

Compute SHA-256 of the source bytes; the unique constraint makes re-imports fail loudly. Repository catches `IntegrityError` and converts to a domain exception.

### Composite uniqueness

```python
__table_args__ = (
    UniqueConstraint("vendor_id", "invoice_number", name="uq_vendor_invoice"),
)
```

A vendor can't have two invoices with the same number; an invoice can't have two lines with the same number.

### Owning relationship pattern

```python
class InvoiceRow(Base):
    line_items: Mapped[list[LineItemRow]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="LineItemRow.line_number",
    )

class LineItemRow(Base):
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"),
        index=True,
    )
    invoice: Mapped[InvoiceRow] = relationship(back_populates="line_items")
```

This is the canonical "aggregate root owns children" pattern. ORM-level cascade + DB-level cascade + ordered collection + indexed FK.

### Optional 1:1 with deferred wiring

```python
class AddressRow(Base):
    vendor: Mapped[VendorRow | None] = relationship(
        back_populates="address",
        uselist=False,
    )

class VendorRow(Base):
    address_id: Mapped[int | None] = mapped_column(
        ForeignKey("addresses.id", ondelete="SET NULL"),
        unique=True,
    )
    address: Mapped[AddressRow | None] = relationship(back_populates="vendor")
```

Vendor optionally has an address; address optionally has a vendor (during the in-between of insertion, or after orphaning). Both annotations honest about nullability.

## 16. The example project's tables.py — annotated highlights

The full file at `src/invoice_importer/storage/tables.py` exemplifies these patterns. Notable choices:

**`AddressRow` separated from `VendorRow`**, true 1:1 relationship. Could also have been flattened onto the vendor; this layout is more normalized but adds a join. Either is defensible.

**`schema="invoice_importer"`** in the `Base` metadata — all tables live in a named schema. Keeps the database tidy and supports multi-app shared databases.

**`ondelete="RESTRICT"`** on `invoices.vendor_id` — vendors with invoices can't be deleted (historical record preservation).

**`ondelete="CASCADE"`** on `line_items.invoice_id` — line items are owned by their invoice.

**`unique=True` on `content_hash`** — idempotency mechanism for re-imports.

**`server_default=func.now()`** on `imported_at` — DB-clock authoritative audit timestamp.

**Composite `UniqueConstraint`** on `(vendor_id, invoice_number)` and `(invoice_id, line_number)` — business invariants enforced at the schema level.

**`order_by="InvoiceLineItemRow.line_number"`** — predictable ordering when accessing `invoice.line_items`.

**Currency stored as `String(3)`, not a DB-level enum** — the `CurrencyCode` enum lives in the domain layer. Trade-off: easier to extend without a migration, at the cost of DB-level enforcement. Also means the adapter can pass `invoice.currency` directly (since `StrEnum` instances *are* strings) — no `.value` needed.

**No `updated_at` on invoices** — they're immutable historical records. Add only when fields can change.

## 17. Greenlet bridging

Async SQLAlchemy uses **greenlets** internally to let sync-looking code perform async I/O. This is what `connection.run_sync(...)` exploits:

```python
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

`metadata.create_all` is a sync function. `run_sync` executes it on a wrapped sync view of the async connection, yielding to the event loop where needed via greenlet switching.

You'll use `run_sync` anywhere a sync-only SQLAlchemy API needs to run in an async context: `create_all`, `drop_all`, Alembic migrations, some reflection operations.

The `greenlet` library is why async SQLAlchemy is gated behind the `[asyncio]` extra — sync-only users don't need to pull it in.

If you ever see a `greenlet_spawn` or "no current greenlet" error, you're calling sync SQLAlchemy code from async context outside of `run_sync`. The fix is to either run it via `run_sync`, or use the proper async API.
