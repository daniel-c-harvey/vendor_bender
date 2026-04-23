# Pydantic & Domain Modeling — Reference Notes

## 1. What Pydantic is

A data validation and serialization library driven by type hints. In v2, the validation engine is written in Rust and is fast.

From one class declaration, Pydantic generates:
- a validating constructor
- JSON (de)serialization
- JSON Schema
- structured error reporting

Conceptually replaces several distinct .NET concerns (FluentValidation + System.Text.Json + Swashbuckle schema generation + IOptions binding) in one unified mechanism.

## 2. Why `BaseModel` works when a plain class doesn't

A plain Python class with only type annotations has **no constructor generated** — annotations are inert metadata stored in `__annotations__`, nothing more.

```python
class Plain:
    name: str

Plain(name="x")   # TypeError: takes no arguments
```

`BaseModel` uses a **metaclass** that runs at class-definition time. It reads the annotations, inspects `Field(...)` metadata, and generates:
- `__init__` accepting declared fields as keyword arguments
- validators and serializers (compiled to Rust internally)
- `model_fields`, `model_dump`, `model_validate`, `model_json_schema`, `__repr__`, `__eq__`

**Same annotation syntax, completely different runtime behavior, because the base class's metaclass machinery processes the annotations.** Plain Python ignores them.

This "annotations as DSL" pattern appears throughout modern Python:
- `@dataclass` (via class decorator)
- `typing.NamedTuple`, `TypedDict` (via metaclass)
- SQLAlchemy 2.0 declarative (`Mapped[T]` via metaclass)
- Django models, attrs, msgspec, and others

**Mental model:** when reading Python data-modeling code, look at the base class. It tells you whether annotations are "real" (annotation-driven generation) or "decorative" (ignored by runtime).

## 3. Required vs. optional vs. nullable

These are three independent concepts in Python's type system. Pydantic respects that separation strictly.

| Declaration | Required? | Can be None? |
|---|---|---|
| `x: str` | yes | no |
| `x: str = ""` | no (defaults to `""`) | no |
| `x: str \| None` | **yes — still required** | yes |
| `x: str \| None = None` | no | yes |

**Key insight:** `X | None` makes the *type* nullable; it does **not** make the field optional. Without a default value, the field must still be supplied — even if only as an explicit `None`.

The idiomatic "truly optional, nullable" field is:
```python
tax_id: str | None = None
```

`Optional[X]` is the old spelling of `X | None` — exactly equivalent. Modern code uses `|`.

## 4. The `Field()` function

Attaches per-field metadata beyond the type: constraints, defaults, documentation, aliases. `Field` with no `default=` is not a default — it's just a constraint bundle on a still-required field.

Common constraints:
- **Strings:** `min_length`, `max_length`, `pattern` (regex)
- **Numbers:** `gt`, `ge`, `lt`, `le`, `multiple_of`
- **Decimals:** `max_digits`, `decimal_places`
- **Collections:** `min_length`, `max_length`

Forms:
```python
# Assignment form — one-off per-field constraints
name: str = Field(min_length=1, max_length=200)

# Assignment form with a default
country: str = Field(default="US", min_length=2, max_length=2)
```

### `Annotated` aliases for reusable constraints

```python
from typing import Annotated
from pydantic import Field

NonEmptyStr200 = Annotated[str, Field(min_length=1, max_length=200)]
Money = Annotated[Decimal, Field(max_digits=14, decimal_places=2, ge=0)]
```

Used as the type itself:
```python
class Vendor(BaseModel):
    name: NonEmptyStr200    # the alias IS the type — do not use as a default
```

**Common early mistake:** writing `name: str = NonEmptyStr200`. The alias is a typing object, not a value; it belongs in the type position, not the default position.

Static type checkers see `NonEmptyStr200` as plain `str` — the `Field(...)` metadata is visible to Pydantic at runtime but invisible to type checkers. Best of both worlds.

## 5. Defaults and mutability

| Scenario | Form |
|---|---|
| Required, any type | `x: T` (no default) |
| Optional, immutable default | `x: T = value` |
| Optional, nullable, defaulting to None | `x: T \| None = None` |
| Optional, mutable default (list/dict/set) | `x: T = Field(default_factory=list)` |
| Optional, empty tuple default | `x: tuple[T, ...] = ()` (immutable, no factory needed) |

**`default_factory` exists to avoid shared-mutable-default bugs.** It is only needed when all three are true:
1. the field is optional (has a default)
2. the default is mutable
3. you want a fresh instance per model instance

Pydantic v2 catches the classic footgun at class-definition time — you cannot write `items: list[str] = []`.

**Required fields need no default machinery at all.** `line_items: tuple[LineItem, ...] = Field(min_length=1)` has no default — the constraint `min_length=1` is just attached to an otherwise-required field. The question "what's the default" doesn't arise.

## 6. Model-level configuration: `model_config`

Whole-model behavior is controlled via a class-level `model_config` attribute using `ConfigDict`:

```python
from pydantic import BaseModel, ConfigDict

class DomainModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )
```

The four settings that matter for domain models:

**`frozen=True`** — instances immutable; assignments raise. Instances become hashable. `model_copy(update={...})` produces a modified copy. Note: the *reference* is frozen; mutable contents (a contained `list`) still allow mutation — use `tuple` inside frozen models for full immutability.

**`extra="forbid"`** — reject unknown fields at validation time. The default `"ignore"` silently drops them, which hides schema drift. Always `"forbid"` for domain models and API contracts. The third option `"allow"` stashes unknowns on `__pydantic_extra__`.

**`str_strip_whitespace=True`** — auto-strip leading/trailing whitespace on all string fields before validation. Combined with `min_length=1`, makes whitespace-only strings fail validation properly.

**`validate_assignment=True`** — re-run validators on attribute assignment. Moot if `frozen=True`; useful for mutable models needing continuous invariants.

### Inheritance for shared config

Define a single base class and inherit:

```python
class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

class Address(DomainModel): ...
class Vendor(DomainModel): ...
```

Policy expressed once, applied everywhere. Later you'd have parallel `ApiModel` or similar bases with different policies for layer boundaries.

## 7. Custom validators

Three kinds, each for a different job.

### `@field_validator("field_name")` — single-field transforms and checks

```python
@field_validator("name")
@classmethod
def no_placeholder_names(cls, v: str) -> str:
    if v.lower() in {"n/a", "unknown"}:
        raise ValueError(f"placeholder name not allowed: {v!r}")
    return v
```

Rules:
- `@classmethod` is required
- must **return the value** (or raise); forgetting to return produces `None`
- raise `ValueError` to reject — Pydantic catches and wraps in `ValidationError`; never construct `ValidationError` yourself
- multiple fields: `@field_validator("name", "tax_id")`

### `@model_validator(mode="after")` — cross-field invariants

```python
@model_validator(mode="after")
def check_dates(self) -> Self:
    if self.due_date and self.due_date < self.issue_date:
        raise ValueError("due_date must be on or after issue_date")
    return self
```

Rules:
- runs after all fields are individually validated
- instance method (takes `self`), not classmethod
- `self` is a fully constructed, fully typed instance
- return `self`
- `-> Self` return annotation (from `typing.Self`, 3.11+) works cleanly in inheritance

### `mode="before"` — normalize raw input before type coercion

Used when input shape doesn't match declared type. Rarely needed in domain models; usually better handled in the extraction layer.

```python
@field_validator("quantity", mode="before")
@classmethod
def parse_quantity(cls, v):
    if isinstance(v, str):
        v = v.strip().split()[0]   # "2 units" -> "2"
    return v   # let Pydantic coerce to Decimal
```

### Execution order

1. `model_validator(mode="before")` — raw dict
2. For each field: `field_validator(mode="before")` → type coercion → `field_validator(mode="after")`
3. `model_validator(mode="after")` — complete typed instance

Multiple validators of the same kind run in declaration order.

## 8. Types for business data

**`Decimal` for money, always.** Floats accumulate binary rounding errors.
- Construct from strings: `Decimal("0.1")`, not `Decimal(0.1)`
- `.quantize(Decimal("0.01"))` rounds to 2 decimal places (banker's rounding by default)
- Tolerances matter: `abs(a - b) > Decimal("0.02")` handles real-world rounding variance

**`date` for calendar dates** (no time component); `datetime` for timestamps. Pydantic accepts ISO 8601 strings and Python instances.

**`StrEnum` (3.11+) for closed string-valued sets:**
```python
class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"
```
Instances *are* strings (`Currency.USD == "USD"` is True), serialize naturally to JSON, and give the type checker a closed set.

**`tuple[X, ...]` for immutable variable-length collections.** The `...` is a literal ellipsis meaning "variable length, elements of type X." Without it, `tuple[int, str]` is a fixed 2-tuple with typed slots.

Pydantic accepts any iterable when validating a tuple field — lists from JSON become tuples on the model.

## 9. Nested models

Models compose transparently:

```python
class Vendor(DomainModel):
    address: Address | None = None
```

- Pydantic validates nested dicts recursively
- Accepts either a model instance or a dict at construction
- Validation errors report full paths: `address.city`, `line_items.0.quantity`
- **Freezing is per-class**, not propagated — every model in the tree needs `frozen=True` for full immutability (or inherit from a shared frozen base)

## 10. Error handling

Pydantic raises `ValidationError` on failed validation with structured details:

```python
try:
    Invoice.model_validate(data)
except ValidationError as e:
    e.errors()   # list of dicts: {type, loc, msg, input, ctx}
    e.json()     # JSON representation
```

Each error has a `loc` tuple with the field path. FastAPI converts these into 422 responses automatically.

**Design principle:** let `ValidationError` propagate across layers unless you're adding meaningful context. Wrap it in a domain-specific error (e.g., `ExtractionError`) only when the *source* of the failure is semantically different and callers need to distinguish.

## 11. Serialization

Output:
```python
invoice.model_dump()                   # dict with Python types
invoice.model_dump(mode="json")        # dict with JSON-compatible types
invoice.model_dump_json()              # JSON string (most efficient)
invoice.model_dump(exclude={...}, include={...}, exclude_none=True, by_alias=True)
```

**Decimal serialization caveat:** `mode="json"` converts `Decimal` to `float`, losing precision. For APIs that need to preserve it, use `@field_serializer` to emit a string:
```python
@field_serializer("grand_total")
def serialize_money(self, v: Decimal) -> str:
    return f"{v:.2f}"
```

### Aliases for API naming conventions

```python
model_config = ConfigDict(
    alias_generator=to_camel,
    populate_by_name=True,
)
```

Python stays snake_case, JSON becomes camelCase. Typical pattern: an `ApiModel` base with the alias generator configured; domain models don't need aliases.

## 12. JSON Schema generation

```python
Invoice.model_json_schema()
```

Produces full JSON Schema from the model. Everything expressible in JSON Schema (types, constraints, nested models, enums, descriptions) appears automatically. Cross-field validators don't appear — JSON Schema can't express them. This is what:
- FastAPI uses to build OpenAPI docs
- LLM APIs consume for structured-output tool calling
- Appian's Integration objects can import as a contract

Closed loop: one Pydantic class is the source of truth for the runtime contract, the API documentation, and the LLM schema.

## 13. Strictness and coercion

Pydantic v2 is lax by default: it coerces `"42"` → `42` for an `int` field, `"true"` → `True` for a `bool`. This is usually what you want for parsing JSON/form input.

Control strictness per-field or per-model:
```python
from pydantic import StrictInt
count: StrictInt     # rejects "42"
# or
model_config = ConfigDict(strict=True)
# or at call site
Invoice.model_validate(data, strict=True)
```

Rule of thumb: strict at trust boundaries (API inputs where the client should know the types); lax for best-effort parsing (LLM outputs, scraped data).

## 14. Design checklist for a domain model

1. **Smallest field set first.** Easier to add than remove.
2. **Right type per field.** `Decimal` for money, `date`/`datetime` for times, enums for closed sets, dedicated types where they exist.
3. **Per-field invariants in `Field(...)`.** Min/max lengths, ranges, patterns.
4. **Cross-field invariants in `model_validator(mode="after")`.**
5. **Value or entity?** Value → `frozen=True`, tuples for collections. Entity with identity and mutable state → usually a storage-layer concern, not a domain model.
6. **Trust level of inputs?** `extra="forbid"` by default.
7. **API serialization?** Aliases, decimal formatting, date formatting — decide early and apply uniformly via a shared base class.

## 15. `*args` / `**kwargs` — the same syntax, two directions

Came up in passing; worth pinning down because it's everywhere.

**In a function definition (collecting):**
```python
def f(*args, **kwargs):    # args=tuple, kwargs=dict
    ...
```

**In a function call (spreading):**
```python
f(*some_list, **some_dict)   # unpack into separate arguments
```

**Forwarding pattern** (decorators, wrappers, cooperative inheritance):
```python
def wrapper(*args, **kwargs):
    return func(*args, **kwargs)
```

Parameter order in signatures: `positional-only, /, positional-or-keyword, *args, keyword-only, **kwargs`. The bare `*` in `def f(x, *, y)` forces `y` to be keyword-only without collecting extras — invaluable for boolean flags and optional config at call sites.
