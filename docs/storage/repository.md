# Repository Layer & Storage Wiring — Reference Notes

Companion to `tables.md`. That doc covers the schema-declaration side of SQLAlchemy; this one covers everything around it: engine/session lifecycle, the adapter pattern, the repository pattern, error handling, and how the layers compose.

## 1. Layer responsibilities

A clean storage layer has four distinct concerns, each in its own module:

| Module | Responsibility |
|---|---|
| `tables.py` | Schema declaration (SQLAlchemy ORM classes) |
| `db.py` | Engine/session/transaction lifecycle |
| `adapters.py` | Translation between domain models and storage rows |
| `repository.py` | Public operations the rest of the app calls |

Outside the `storage/` package, **no code should import SQLAlchemy.** The repository functions are the seam. Routes, CLIs, extraction pipelines speak `Invoice`, `Vendor`, `Address` — domain types only.

## 2. Engine and session lifecycle (`db.py`)

Two distinct objects with distinct lifecycles, packaged into three pure functions.

### Engine — long-lived

Created once per application at startup. Holds the connection pool. Not transactional.

```python
def make_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(url, echo=echo, pool_pre_ping=True)
```

- `pool_pre_ping=True` — verifies connections before checkout. Small latency cost, survives DB restarts.
- `echo=True` — logs every SQL statement. Useful in development; off in production.
- `*, echo` — keyword-only argument. `make_engine(url, True)` would be unreadable; `make_engine(url, echo=True)` is self-documenting.

The `Engine` is thread/task-safe. Share one instance across the whole application.

### Session factory — long-lived

Bound to the engine, produces sessions on demand.

```python
def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

`expire_on_commit=False` is **mandatory for async**. The default expires loaded attributes after commit, causing the next access to silently re-fetch — which would need to await, which sync attribute access can't do, which crashes.

### Session — short-lived

One per logical operation: per request, per CLI command, per test, per batch job. **Never long-lived. Never shared across requests.**

The `transactional_session` context manager creates and disposes them with proper transaction handling.

### The transactional_session pattern

```python
@asynccontextmanager
async def transactional_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

Properties:

- **Caller-owned transaction.** The `transactional_session` context manager defines the transaction boundary. Repository functions inside it don't commit.
- **Commit on success, rollback on exception.** Atomic by default — the entire block either succeeds or rolls back.
- **One session per `async with` block.** No long-lived sessions; no sharing.

Usage:

```python
async with transactional_session(session_factory) as session:
    await repository.save_thing(session, thing)
    await repository.update_other(session, ...)
    # both succeed atomically, or both roll back
```

This is the equivalent of a using-block around a `DbContext` plus an explicit transaction in .NET.

## 3. Adapters (`adapters.py`)

Translation between Pydantic domain models and SQLAlchemy rows. The most overlooked part of a clean storage layer.

### Why hand-written, not auto-mapped

Tempting to write:
```python
return InvoiceRow(**invoice.model_dump())   # DON'T
```

Don't. The shapes will diverge in real projects:
- Currency as enum (domain) vs. string (storage)
- Tuples (immutable domain) vs. lists (mutable ORM collections)
- Computed/transient fields that exist only in the domain
- Audit/provenance fields (`imported_at`, `content_hash`) that exist only in storage
- Different nullability for fields with defaults on one side

Hand-written adapters surface these differences explicitly. When you add a field to the domain model, you choose deliberately whether to persist it. When you add a column to the schema, you choose deliberately how it reaches the domain.

### Symmetric pair pattern

For each entity, two functions:

```python
def to_address_row(addr: Address) -> AddressRow:
    return AddressRow(
        line1=addr.line1,
        line2=addr.line2,
        city=addr.city,
        region=addr.region,
        postal_code=addr.postal_code,
        country=addr.country,
    )

def from_address_row(row: AddressRow) -> Address:
    return Address(
        line1=row.line1,
        line2=row.line2,
        city=row.city,
        region=row.region,
        postal_code=row.postal_code,
        country=row.country,
    )
```

Symmetry makes maintenance straightforward — when fields change, you update both halves.

### Naming convention

- `to_<thing>_row(...)` — domain → storage
- `from_<thing>_row(...)` — storage → domain
- Public (no underscore prefix) — these are utilities the repository calls directly

Some projects mark them private (`_to_address_row`); both are defensible. Public names mean the repository module imports them clearly; private names emphasize they're not for callers outside `storage/`.

### Compositional translation

For nested structures, adapters delegate:

```python
def to_vendor_row(vendor: Vendor) -> VendorRow:
    return VendorRow(
        name=vendor.name,
        tax_id=vendor.tax_id,
        address=to_address_row(vendor.address) if vendor.address else None,
    )
```

The conditional handles the optional nested model. Same pattern in the reverse direction.

### Operation-aware adapters

The invoice adapter takes provenance fields the domain model doesn't carry, and accepts a pre-existing vendor row to reuse:

```python
def to_invoice_row(
    invoice: Invoice,
    source_identifier: str,
    content_hash: str,
    *,
    vendor: VendorRow | None = None,
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
```

Patterns:

**Provenance as parameters.** `source_identifier` and `content_hash` aren't fields on the domain `Invoice` — they're things the *importer* knows. The adapter takes them as additional parameters and threads them into the row.

**Optional pre-existing vendor.** When the repository has already done a get-or-create for the vendor, it passes the existing `VendorRow` rather than letting the adapter build a fresh one (which would try to insert a duplicate). The `*,` makes `vendor` keyword-only — clarifies intent at the call site.

**`StrEnum` passes through directly.** `currency=invoice.currency` works without `.value` because `StrEnum` instances *are* strings. SQLAlchemy stores the string value either way.

### Reverse adapter handles enum reconstruction

```python
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
```

- **`CurrencyCode(row.currency)`** — the explicit string-to-enum conversion. The reverse direction needs this because Pydantic validates the enum value, while the storage column was just a `String(3)`.
- **`tuple(...)`** for the line items — `Invoice.line_items` is `tuple[InvoiceLineItem, ...]` (immutable in the frozen Pydantic model). The list-comprehension generator gets wrapped to satisfy the type.

## 4. The repository pattern in Python

Functions, not classes. Module-level async functions taking the session as a parameter.

```python
async def save_invoice(
    session: AsyncSession,
    invoice: Invoice,
    *,
    source_identifier: str,
    content: bytes,
) -> InvoiceRow:
    ...
```

### Why functions over classes

- **No DI ceremony.** Functions with explicit parameters are testable without containers or mocks.
- **No hidden state.** A function with a session parameter is exactly what it appears to be.
- **Composition is trivial.** Repository functions call other repository functions; they all share the same passed-down session.
- **More Pythonic.** Modern Python codebases predominantly use this style.

You *can* write classes if you prefer encapsulation. Some teams do. The function-with-session-parameter style is dominant in modern code and pairs naturally with FastAPI's `Depends` system.

### Discipline rules

1. **Sessions are passed in, never created internally.** The orchestration layer (route handler, CLI entry, batch job) creates the session via `transactional_session` and passes it down.
2. **Repositories don't commit.** They `add`, `query`, `flush` (when needed for generated IDs), but never `commit`. The caller owns the transaction boundary.
3. **Repositories speak in domain types on their public surface.** Internally they translate via adapter functions; outside, they accept and return Pydantic models (or domain types like raw bytes for content hashing).
4. **Domain errors, not SQL errors.** Translate `IntegrityError` to `DuplicateInvoiceError` etc. before re-raising. Callers shouldn't have to catch SQLAlchemy exceptions.

## 5. Common repository operations

### Get-or-create

```python
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
    await session.flush()    # populate vendor_row.id
    return vendor_row
```

Notes:
- **`session.flush()`** writes to the DB without committing. Necessary to populate auto-generated IDs (`row.id` is `None` until flush).
- **`joinedload`** on the lookup ensures the address is hydrated for any caller that needs it.
- **Race condition exists** between `scalar` and `flush` — two concurrent calls might both miss and both insert. For serial workloads, ignore. For concurrent workloads, retry on `IntegrityError` or use `INSERT ... ON CONFLICT`.

### Save with idempotency and error translation

```python
async def save_invoice(
    session: AsyncSession,
    invoice: Invoice,
    *,
    source_identifier: str,
    content: bytes,
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
        invoice, source_identifier, content_hash, vendor=vendor_row
    )
    session.add(invoice_row)
    
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise DuplicateInvoiceError(
            vendor=invoice.vendor.name,
            invoice_number=invoice.invoice_number,
        ) from e
    
    return invoice_row
```

Patterns:
- **Pre-check for duplicates** before attempting insert. Cheaper than catching `IntegrityError`, and produces cleaner error semantics.
- **Translate `IntegrityError` to domain error.** `from e` preserves the cause for debugging.
- **`await session.rollback()` after IntegrityError** — the failed flush leaves the session in an aborted state. You can't reuse it without rollback.
- **`select(InvoiceRow.id)`** rather than `select(InvoiceRow)` for the duplicate check — only fetches the ID column, not the whole row. Cheap existence check.

### Load with full hydration

```python
async def get_invoice_by_id(
    session: AsyncSession,
    invoice_id: int,
) -> Invoice:
    """Load an invoice by ID, fully hydrated. Raises if not found."""
    row = await session.scalar(
        select(InvoiceRow)
        .where(InvoiceRow.id == invoice_id)
        .options(
            joinedload(InvoiceRow.vendor).joinedload(VendorRow.address),
            selectinload(InvoiceRow.line_items),
        )
    )
    if row is None:
        raise InvoiceNotFoundError(invoice_id)
    return from_invoice_row(row)
```

Patterns:
- **Always eager-load what the adapter needs.** The translation function will access relationships; without eager loading, those access trigger `MissingGreenlet` in async.
- **`joinedload` for scalars, `selectinload` for collections.** Chained for nested.
- **Raise domain error for not-found.** Don't return `None` from public repository functions when not-found is meaningful — make the caller explicit about the scenario via try/except.

### List with filtering

```python
async def list_invoices_for_vendor(
    session: AsyncSession,
    vendor_name: str,
    *,
    limit: int = 100,
) -> list[Invoice]:
    """List recent invoices for a vendor, most recent first."""
    rows = (await session.scalars(
        select(InvoiceRow)
        .join(VendorRow)
        .where(VendorRow.name == vendor_name)
        .order_by(InvoiceRow.issue_date.desc())
        .limit(limit)
        .options(
            joinedload(InvoiceRow.vendor).joinedload(VendorRow.address),
            selectinload(InvoiceRow.line_items),
        )
    )).all()
    return [from_invoice_row(row) for row in rows]
```

Patterns:
- **`.join(VendorRow)`** — SQLAlchemy infers the join condition from the FK relationship. Explicit form: `.join(VendorRow, InvoiceRow.vendor_id == VendorRow.id)`.
- **Keyword-only `limit`** — `*, limit: int = 100` forces callers to write `limit=20`, avoiding positional-bool/int hell.
- **List comprehension at the boundary** — `[from_invoice_row(row) for row in rows]` is the standard "translate everything" pattern.

## 6. Domain errors

Define a base class plus specific cases:

```python
class InvoiceImporterError(Exception):
    """Base for all domain-level errors."""

class VendorNotFoundError(InvoiceImporterError):
    def __init__(self, identifier: str | int) -> None:
        self.identifier = identifier
        super().__init__(f"Vendor not found: {identifier!r}")

class InvoiceNotFoundError(InvoiceImporterError):
    def __init__(self, identifier: str | int) -> None:
        self.identifier = identifier
        super().__init__(f"Invoice not found: {identifier!r}")

class DuplicateInvoiceError(InvoiceImporterError):
    def __init__(self, vendor: str, invoice_number: str) -> None:
        self.vendor = vendor
        self.invoice_number = invoice_number
        super().__init__(
            f"Invoice {invoice_number!r} from {vendor!r} already imported"
        )

class DuplicateContentError(InvoiceImporterError):
    def __init__(self, content_hash: str) -> None:
        self.content_hash = content_hash
        super().__init__(f"Content with hash {content_hash[:16]}... already imported")
```

Patterns:

- **One base class** lets callers `except InvoiceImporterError` to catch all domain failures.
- **Specific subclasses for distinct cases.** Different recovery paths, different exception types.
- **Carry structured data on the exception**, not just a message string. Callers can read `e.vendor`, `e.invoice_number`, `e.content_hash`. Same pattern as .NET exception properties.
- **Translate at the layer boundary.** SQL `IntegrityError` → domain `DuplicateInvoiceError`. Network errors don't get wrapped — those genuinely are infrastructure failures.

## 7. Result extraction patterns

The four ways to consume a `Result`:

| Want | Method | Returns | Use when |
|---|---|---|---|
| Many rows | `(await session.scalars(stmt)).all()` | `list[Model]` | Lists, pagination, bulk |
| Many rows, lazy | `await session.scalars(stmt)` (iterate) | iterator | Streaming large results |
| Exactly one | `(await session.execute(stmt)).scalar_one()` | `Model` | Invariant lookup |
| At most one | `await session.scalar(stmt)` | `Model \| None` | Optional lookup |
| By PK | `await session.get(Model, pk)` | `Model \| None` | PK lookup, hits identity map |

Pyright requires explicit handling of `Optional` returns:

```python
vendor = await session.scalar(stmt)
if vendor is None:
    raise VendorNotFoundError(name)
# pyright now sees vendor: VendorRow (narrowed)
```

If you're writing `assert vendor is not None` as a workaround on a query you *know* should always succeed, switch to `scalar_one()` and let `NoResultFound` speak for the invariant.

## 8. Eager loading: the async-mandatory rule

In async SQLAlchemy, lazy loading is **disabled** because attribute access can't await. Accessing a relationship without eager loading raises `MissingGreenlet`.

Two strategies:

**`selectinload(Relationship)`** — separate `SELECT WHERE FK IN (...)` query. Two queries total, both indexed. Best for **collections**.

**`joinedload(Relationship)`** — `LEFT OUTER JOIN`, single query, parent rows duplicated for each child. Best for **scalars**.

Combine:

```python
.options(
    joinedload(InvoiceRow.vendor).joinedload(VendorRow.address),
    selectinload(InvoiceRow.line_items),
)
```

Chain into nested:

```python
.options(
    selectinload(VendorRow.invoices)
        .selectinload(InvoiceRow.line_items),
)
```

Default rule: **eager-load anything the adapter will touch.** If `from_invoice_row(row)` reads `row.vendor.address` and `row.line_items`, the query that loaded `row` must `joinedload` the vendor (and its address) and `selectinload` the line items.

## 9. The orchestration layer

The seam where transactions begin and repository operations compose:

```python
async def import_invoice(
    session_factory: async_sessionmaker[AsyncSession],
    pdf_bytes: bytes,
    source: str,
    invoice: Invoice,
) -> Invoice:
    async with transactional_session(session_factory) as session:
        invoice_row = await repository.save_invoice(
            session,
            invoice,
            source_identifier=source,
            content=pdf_bytes,
        )
        return await repository.get_invoice_by_id(session, invoice_row.id)
```

Patterns:
- **The session factory comes in as a parameter.** Higher layers (FastAPI lifespan, CLI entry) construct it once and pass it down.
- **One transaction wraps multiple repository calls.** Atomic by construction.
- **Cross-cutting concerns live here, not in repositories.** Logging, metrics, tracing belong at the orchestration boundary.

## 10. The `__init__.py` re-export pattern

A typical pattern is to re-export the public API from the submodules via `storage/__init__.py`:

```python
# src/invoice_importer/storage/__init__.py
from invoice_importer.storage.db import (
    make_engine,
    make_session_factory,
    transactional_session,
)
from invoice_importer.storage.repository import (
    get_invoice_by_id,
    get_or_create_vendor,
    list_invoices_for_vendor,
    save_invoice,
)

__all__ = [
    "get_invoice_by_id",
    "get_or_create_vendor",
    "list_invoices_for_vendor",
    "make_engine",
    "make_session_factory",
    "save_invoice",
    "transactional_session",
]
```

Now callers write `from invoice_importer.storage import save_invoice` instead of `from invoice_importer.storage.repository import save_invoice`. The internal module structure stays flexible behind a stable public surface.

This is the same instinct as a C# `internal` class with a `public` facade — keep your implementation flexible behind a stable public surface.

## 11. Testing

Repository functions take a session — tests pass a session backed by in-memory SQLite. No mocking required.

```python
@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_save_and_load(db_session):
    invoice = make_test_invoice()  # build a domain Invoice
    row = await repository.save_invoice(
        db_session, invoice, source_identifier="x", content=b"y"
    )
    await db_session.commit()
    
    loaded = await repository.get_invoice_by_id(db_session, row.id)
    assert loaded.vendor.name == invoice.vendor.name
    assert len(loaded.line_items) == len(invoice.line_items)
```

Notes:
- **In-memory SQLite for unit tests.** Fast, no setup, fresh per test.
- **Real PG for integration tests.** Catches PG-specific behavior SQLite can't replicate.
- **`create_all` in tests, migrations in production.** Tests don't need migration overhead; production needs migration safety.

The PG-specific `schema="invoice_importer"` setting on `Base.metadata` doesn't translate to SQLite (which has no schemas). Tests against SQLite either skip the schema or work around it.

## 12. The seam: what the rest of the app sees

Outside `storage/`, importing looks like:

```python
from invoice_importer.storage import (
    transactional_session,
    save_invoice,
    get_invoice_by_id,
)
from invoice_importer.domain.errors import (
    DuplicateContentError,
    DuplicateInvoiceError,
    InvoiceNotFoundError,
)
```

Note what's **not** imported: SQLAlchemy itself, `IntegrityError`, `AsyncSession`, `select`, the `*Row` classes. The rest of the app doesn't know storage uses SQLAlchemy. If you swap to a different ORM, document database, or even a file-based store later, you change the storage package internals; everything else keeps working.

This is the value of the layer split. The discipline costs a small amount up front and pays off forever.

## 13. Composition example

The full flow of importing an invoice, with cross-layer connections highlighted:

```python
# 1. Orchestration (FastAPI route, CLI, etc.)
async with transactional_session(session_factory) as session:
    
    # 2. Repository: domain operation
    invoice_row = await repository.save_invoice(
        session,
        invoice,                                    # Pydantic Invoice
        source_identifier="path/to/pdf",
        content=pdf_bytes,
    )
    # Inside save_invoice:
    #   - hashlib.sha256(content).hexdigest() — content hash
    #   - select(...) — duplicate check, raises DuplicateContentError
    #   - get_or_create_vendor() — recursive repository call
    #   - to_invoice_row(...) — adapter that builds InvoiceRow
    #     - to_line_item_row(...) for each line
    #     - reuses pre-existing vendor_row
    #   - session.add() + session.flush() — pending in transaction
    #   - IntegrityError → DuplicateInvoiceError translation
    
    # 3. Optional re-read for confirmation
    saved = await repository.get_invoice_by_id(session, invoice_row.id)
    # Inside get_invoice_by_id:
    #   - select with joinedload/selectinload
    #   - from_invoice_row(...) — full graph translation back to domain
    #   - InvoiceNotFoundError if absent

# 4. transactional_session commits or rolls back here
```

Each layer has one job. Each function reads obviously. Errors are typed and meaningful. Tests substitute a SQLite session and run instantly.

## 14. Anti-patterns

**Don't commit in repository functions.** Composition breaks; transactions become impossible.

**Don't share sessions across requests.** They're not thread-safe, and they accumulate state.

**Don't catch SQLAlchemy exceptions in callers.** Translate them at the repository boundary; let only domain exceptions cross the seam.

**Don't return `None` from public repository functions when not-found is the meaningful case.** Raise a domain error; force callers to handle it explicitly.

**Don't auto-map between domain and storage with `**model.model_dump()`.** The shapes diverge; hand-written adapters expose those differences explicitly.

**Don't access relationships in async without eager loading.** Crashes loudly with `MissingGreenlet` — but only at the access site, which can be far from where the query was written. Eager-load proactively.

**Don't put business logic in repositories.** Validation belongs to the domain (Pydantic validators); orchestration belongs to the calling layer. Repositories are storage adapters, nothing more.

**Don't forget to `await session.rollback()` after catching `IntegrityError`.** A failed flush leaves the session aborted; you can't reuse it without rollback.

## 15. Quick reference table

| Operation | Pattern |
|---|---|
| Setup engine + factory | `make_engine(url)`, `make_session_factory(engine)` once at startup |
| Open transaction + session | `async with transactional_session(factory) as session:` |
| Get by primary key | `await session.get(Model, pk)` |
| Get optional by criteria | `await session.scalar(select(...).where(...))` |
| Get required by criteria | `(await session.execute(stmt)).scalar_one()` |
| List | `(await session.scalars(stmt)).all()` |
| Insert | `session.add(row); await session.flush()` (for ID) |
| Update tracked entity | mutate attributes; flush/commit auto-syncs |
| Delete | `await session.delete(row)` |
| Eager-load scalar | `.options(joinedload(Model.relationship))` |
| Eager-load collection | `.options(selectinload(Model.relationship))` |
| Translate IntegrityError | `try / except IntegrityError → raise DomainError from e` |
