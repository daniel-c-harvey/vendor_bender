# Python 3 Cheat Sheet (for C#/TS devs)

## Typing system essentials

Types are **gradual + runtime-erased**. Checker (pyright/mypy) is separate from runtime. Use Pydantic/attrs for runtime validation at IO boundaries.

```python
name: str = "Daniel"
age: int | None = None                      # 3.10+; else Optional[int]
def greet(name: str, loud: bool = False) -> str: ...
```

| Concept | Syntax |
|---|---|
| Union | `int \| str` (3.10+) / `Union[int, str]` |
| Optional | `str \| None` / `Optional[str]` |
| Builtin generics | `list[int]`, `dict[str, int]`, `tuple[int, ...]` |
| Generics (old) | `T = TypeVar("T"); class Repo(Generic[T]): ...` |
| Generics (PEP 695, 3.12+) | `class Repo[T]: ...` / `def first[T](xs: list[T]) -> T \| None` |
| Structural iface | `class SupportsWrite(Protocol): def write(self, b: bytes) -> int: ...` |
| Literal | `Literal["a", "b"]` |
| TypedDict | `class User(TypedDict): id: int; name: str` |
| Nominal wrapper | `UserId = NewType("UserId", int)` |
| Narrowing | `isinstance`, `is None`, `TypeGuard`, `TypeIs` (3.13+) |
| Escape hatches | `Any`, `cast(T, x)`, `# type: ignore[code]` |
| Self-type | `typing.Self` (3.11+) or `"ClassName"` forward ref |

**Gotchas:** annotations don't enforce at runtime • `isinstance(x, list[int])` raises • `None` = void • default value ≠ Optional • `@overload` is checker-only.

## Built-in types → .NET

| Python | .NET |
|---|---|
| `int` | `long` (arbitrary precision) |
| `float` | `double` |
| `bool` | `bool` (subclass of `int`) |
| `str` | `string` (immutable) |
| `bytes` / `bytearray` | `byte[]` immutable / mutable |
| `list` | `List<T>` |
| `tuple` | `ValueTuple` |
| `dict` | `Dictionary<K,V>` (ordered since 3.7) |
| `set` / `frozenset` | `HashSet<T>` / immutable |
| `None` | `null` (singleton, type `NoneType`) |
| `range` | `Enumerable.Range` (lazy) |

## str

```python
s.split(",")  s.rsplit(",", 1)  ",".join(items)
s.strip() / lstrip() / rstrip()
s.startswith(x)  s.endswith(x)  x in s
s.replace(a, b)  s.removeprefix(x)  s.removesuffix(x)
s.lower() / upper() / casefold() / title()
s.find(x)  s.rfind(x)  s.index(x)         # index raises
s.count(x)  len(s)
s.encode("utf-8")  b.decode("utf-8")
f"{name=} {x:.2f} {n:,} {x:>10} {dt:%Y-%m-%d}"
```

## list

```python
xs.append(x)  xs.extend(it)  xs.insert(i, x)
xs.pop()  xs.pop(0)  xs.remove(x)
xs.sort(key=..., reverse=True)  sorted(xs)
xs.reverse()  reversed(xs)
xs.index(x)  xs.count(x)  xs.clear()
xs[2:5]  xs[::-1]  xs[::2]  xs[:]           # slice/copy
```

## dict

```python
d[k]                    # raises KeyError
d.get(k, default)       # safe
d.setdefault(k, [])
d.pop(k, default)
d.keys() / values() / items()
k in d  len(d)  d.clear()
d | other   d |= other   {**a, **b}          # 3.9+ merge
dict.fromkeys(keys, 0)
```

## set

```python
s.add(x)  s.discard(x)  s.remove(x)
s | t    s & t    s - t    s ^ t             # union/&/diff/symdiff
s.issubset(t)  s.issuperset(t)  s.isdisjoint(t)
```

## tuple

```python
t = (1, "a")   x, y = t   a, *rest = t
# Named: NamedTuple or @dataclass(frozen=True)
```

## Comprehensions (replaces LINQ)

```python
[x*2 for x in xs if x > 0]        # list
{x*2 for x in xs}                  # set
{k: v for k, v in pairs}           # dict
(x*2 for x in xs)                  # generator (lazy)
```

## itertools (lazy combinators)

```python
chain(a, b)   chain.from_iterable(lists)
zip(a, b, strict=True)             # 3.10+
enumerate(xs, start=0)
islice(xs, start, stop, step)
takewhile(pred, xs)  dropwhile(pred, xs)
groupby(xs, key=...)               # needs pre-sorted input
accumulate(xs, operator.add)
product(a, b)  permutations(xs, r)  combinations(xs, r)
count(start, step)  cycle(xs)  repeat(x, n)
pairwise(xs)        # 3.10+
batched(xs, n)      # 3.12+
```

## functools

```python
reduce(f, xs, init)
partial(f, x=1)
@lru_cache(maxsize=128)   @cache
@cached_property
@singledispatch          # type-based overloading
```

## collections

```python
Counter(iterable)       # .most_common(n), arithmetic
defaultdict(list)
deque(maxlen=100)       # O(1) appendleft/popleft
namedtuple("Point", "x y")   # prefer NamedTuple/dataclass
ChainMap(a, b)
```

## pathlib (prefer over os.path)

```python
p = Path("~/src/app").expanduser()
p / "sub" / "file.txt"
p.exists()  p.is_file()  p.is_dir()
p.read_text()  p.write_text(s)
p.read_bytes()  p.write_bytes(b)
p.stem  p.suffix  p.name  p.parent  p.parents
p.with_suffix(".bak")  p.with_name("x.txt")
p.glob("*.py")  p.rglob("*.py")
p.iterdir()  p.mkdir(parents=True, exist_ok=True)
p.resolve()  Path.cwd()  Path.home()
```

## datetime

```python
from datetime import datetime, date, time, timedelta, UTC
from zoneinfo import ZoneInfo                # named TZs

datetime.now(UTC)                            # always aware
datetime.fromisoformat(s)   dt.isoformat()
date.today()   date(2026, 4, 23)
dt + timedelta(days=1, hours=2)
dt.astimezone(ZoneInfo("America/New_York"))
dt.strftime("%Y-%m-%d")   datetime.strptime(s, "%Y-%m-%d")
```

## json

```python
json.dumps(obj, indent=2, default=str)
json.loads(s)
json.dump(obj, file)   json.load(file)
# Nontrivial: use Pydantic or dataclasses.asdict
```

## re

```python
re.match(pat, s)       # anchored start
re.search(pat, s)      # anywhere
re.fullmatch(pat, s)
re.findall / finditer / sub / split
p = re.compile(r"...", re.IGNORECASE | re.MULTILINE)
m.group(0)  m.group(1)  m.groupdict()  m.span()
# Always use r"..." raw strings
```

## os / sys / subprocess

```python
os.environ.get("KEY", default)
os.getcwd()  os.chdir(p)
sys.argv  sys.exit(1)  sys.version_info
subprocess.run(["ls", "-la"], capture_output=True, text=True, check=True)
```

## io / context managers

```python
with open(path, "r", encoding="utf-8") as f:
    data = f.read()
# Modes: r w a (+ b binary, + read/write). Always specify encoding.
```

## contextlib

```python
with contextlib.suppress(FileNotFoundError):
    p.unlink()

@contextlib.contextmanager
def timed():
    t0 = time.perf_counter(); yield
    print(time.perf_counter() - t0)
```

## typing quick ref

```python
Any, Optional[T], Union[A, B], Literal["a", "b"]
Callable[[int, str], bool]
Iterable[T], Iterator[T], Sequence[T], Mapping[K, V], MutableMapping[K, V]
TypedDict, NamedTuple, Protocol, runtime_checkable
TypeVar, Generic, Self, TypeGuard, TypeIs
Final, ClassVar, Annotated
cast, overload, assert_never
```

## dataclasses

```python
from dataclasses import dataclass, field, asdict, replace

@dataclass(frozen=True, slots=True, kw_only=True)
class User:
    id: int
    name: str
    tags: list[str] = field(default_factory=list)

replace(user, name="x")        # record-with-expression equivalent
```

## enum

```python
from enum import Enum, IntEnum, StrEnum, auto

class Status(StrEnum):
    Active = "active"
    Disabled = "disabled"
```

## logging

```python
import logging
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)
log.info("started %s", name)    # lazy % formatting
```

## asyncio

```python
async def fetch(url): ...
asyncio.run(main())
await asyncio.gather(a(), b())
async with aiohttp.ClientSession() as s: ...
async for item in stream: ...

async with asyncio.TaskGroup() as tg:        # 3.11+ structured concurrency
    tg.create_task(a())
    tg.create_task(b())

async with asyncio.timeout(5): ...           # 3.11+
```

## Built-ins you'll reach for

```python
len  range  enumerate  zip  map  filter  sorted  reversed
sum  min  max  any  all  abs  round  divmod  pow
isinstance  issubclass  hasattr  getattr  setattr  delattr
iter  next  callable  id  hash  repr  vars  dir
print  input  open  type
```

## .NET-isms that don't exist

| .NET | Python |
|---|---|
| LINQ | comprehensions + `itertools` + generators |
| `StringBuilder` | `"".join(parts)` |
| `var` / `let` | names exist on assignment |
| `null` / `== null` | `None` / `is None` |
| `switch` (pre-3.10) | `match`/`case` (3.10+, structural, F#-like) |
| `using` | `with` blocks (`__enter__`/`__exit__`) |
| `private` | `_name` convention; `__name` mangled |

## Tooling worth knowing

- **pyright** (Pylance) — fast, strict, best errors. TS-aesthetic; enable strict mode.
- **mypy** — PEP reference impl, slower, entrenched.
- **Pydantic v2** — runtime validation at IO boundaries (Rust core).
- **dataclasses** — stdlib; **attrs** — richer third-party; **Pydantic** — validated.
- Treat `Any` like C# `dynamic`: only at untyped edges.
