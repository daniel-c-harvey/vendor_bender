# Python Project Structure Cheatsheet

Reference for layout, entry points, and the differences between scripts, applications, packages, and libraries in modern Python.

## The four shapes

What you're building determines how you lay it out and how users invoke it.

| Shape | Purpose | Distribution | Invocation |
|---|---|---|---|
| **Script** | One-off task, glue code | Single `.py` file | `python script.py` |
| **Application** | Standalone program with internal structure | Source repo, possibly packaged | `python -m app` or installed CLI |
| **Package** | Reusable code organized into modules | Published to PyPI or internal index | `import package` |
| **Library** | Same as package, framed as "consumed by other code" | Published to PyPI | `import lib` |

The lines between **package** and **library** are blurry — both are importable code distributed for reuse. "Library" usually implies stable public API and broader consumption.

## Script

The simplest. Single file, no project structure.

```
my_tool.py
```

```python
# my_tool.py
import sys

def main(argv: list[str]) -> int:
    print(f"Hello, {argv[1] if len(argv) > 1 else 'world'}")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

**When to use:** prototypes, automation glue, one-off computations. If it's under ~100 lines and has no internal modules, keep it a script.

**Limits:** no virtual environment isolation by default, no version pinning, can't easily ship to others. Outgrows itself fast.

**uv even helps with single scripts.** Inline metadata (PEP 723):

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["httpx"]
# ///
import httpx
print(httpx.get("https://example.com").status_code)
```

Run: `uv run my_tool.py`. uv reads the inline block, sets up a temporary environment, runs it. Useful for sharable scripts that have real dependencies but don't deserve a full project.

## Application

A program meant to be run, not imported. Has internal structure but its public face is a CLI or web service, not an importable API.

### Layout

```
invoice-importer/
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
├── README.md
├── src/
│   └── invoice_importer/
│       ├── __init__.py
│       ├── __main__.py          # `python -m invoice_importer` entry
│       ├── cli.py               # CLI entry function (main)
│       ├── config.py
│       ├── domain/
│       │   ├── __init__.py
│       │   └── models.py
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── tables.py
│       │   └── repository.py
│       └── ...
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── migrations/                   # Alembic, if applicable
    └── versions/
```

Bootstrap with: `uv init --app --package <name>` (or just `uv init` and add `--package`).

### Why `src/` layout?

Without `src/`, importing `invoice_importer` works because the project root is on `sys.path` — but only by accident. Tests pass because Python finds the package in the repo root, not because the package is properly installed.

With `src/`, the package only resolves after it's installed (`uv sync` does this in editable mode). This means tests run against the installed package the same way real users will see it. Catches packaging bugs early.

**Use `src/` for every new project.** `uv init` does this by default.

### `__init__.py` — what it is

A file (often empty) that marks a directory as a Python *package*. Without it, the directory is a "namespace package" — different rules, weirder behavior, mostly to be avoided.

```python
# src/invoice_importer/__init__.py
# can be empty, or:
__version__ = "0.1.0"

# can re-export for convenience:
from invoice_importer.domain.models import Invoice, Vendor
```

Re-exports are useful when consumers should write `from invoice_importer import Invoice` instead of `from invoice_importer.domain.models import Invoice`. Use sparingly — every re-export is API surface you're committing to.

### `__main__.py` — package as program

Lets you run the package directly:

```powershell
python -m invoice_importer
uv run python -m invoice_importer
```

```python
# src/invoice_importer/__main__.py
from invoice_importer.cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
```

Always thin — just dispatches to `cli.main()`. The actual logic lives elsewhere so it's testable.

### `cli.py` — the entry function

```python
# src/invoice_importer/cli.py
import argparse
import asyncio
import logging
import sys


async def run(args: argparse.Namespace) -> int:
    # the actual work
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="invoice-import")
    parser.add_argument("--source", required=True)
    args = parser.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
```

Conventions worth following:
- `main(argv=None)` — pass `argv` so tests can inject; default to `None` so argparse uses `sys.argv` naturally.
- `main()` returns an exit code; the wrapper does `sys.exit(main())`.
- `logging.basicConfig` early.
- Async work goes in `run()`; `main()` is sync and dips into async via `asyncio.run`.

### Console scripts in `pyproject.toml`

The polished way to ship a CLI: declare entry points.

```toml
[project.scripts]
invoice-import = "invoice_importer.cli:main"
```

After `uv sync`, an executable `invoice-import` is installed in `.venv/bin/` (or `Scripts/` on Windows). Run with:

```powershell
uv run invoice-import --source ./pdfs
```

Three ways to invoke the same code, all equivalent:
1. `uv run python -m invoice_importer` — works because of `__main__.py`
2. `uv run invoice-import` — works because of `[project.scripts]`
3. `uv run python src/invoice_importer/cli.py` — works because of `if __name__ == "__main__":` guard

For users, option 2 is cleanest. For development and module discovery, option 1 is most explicit.

## Package / Library

Reusable code consumed by other Python projects via `import`. Published to PyPI or an internal index.

### Layout

Almost identical to an application, but typically:
- No `__main__.py` (not run directly)
- No `[project.scripts]` (no CLI to install)
- Public API carefully curated in top-level `__init__.py`
- More attention to versioning and stable interfaces

```
my-lib/
├── pyproject.toml
├── uv.lock
├── README.md
├── src/
│   └── my_lib/
│       ├── __init__.py          # public API surface
│       ├── _internal.py         # underscore-prefixed = private
│       └── ...
└── tests/
```

Bootstrap with `uv init --lib <name>`.

### `pyproject.toml` differences

```toml
[project]
name = "my-lib"
version = "0.1.0"
requires-python = ">=3.10"      # libraries usually support older Pythons
dependencies = [...]              # keep minimal; users pay for every dep

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

For libraries: be conservative with `requires-python` (broad support), be conservative with `dependencies` (minimize surface), pin lower bounds carefully (let users upgrade transitive deps).

For applications: pin tight, use the latest Python, pull whatever deps you want — you control deployment.

### Public API conventions

Anything not exported in `__init__.py` is implicitly internal. Underscore-prefixed names (`_internal.py`, `_helper`) are conventionally private even if technically importable.

```python
# src/my_lib/__init__.py
from my_lib.core import process, Result
from my_lib.errors import MyLibError

__all__ = ["process", "Result", "MyLibError"]
```

`__all__` controls what `from my_lib import *` brings in, and signals intended public API. Tools like Sphinx and pyright use it for API documentation.

### Versioning

Libraries follow [Semantic Versioning](https://semver.org/) by convention:
- `0.x.y` — pre-stable, anything can change
- `1.0.0` — first stable release; public API is committed
- `MAJOR.MINOR.PATCH` after that:
  - PATCH: bug fixes, no API change
  - MINOR: new features, backward-compatible
  - MAJOR: breaking changes

Applications version however they want; users don't `pip install` an application's specific version against a constraint.

## `pyproject.toml` reference

The single configuration file for any Python project. Modern standard (PEP 621).

### Minimal app

```toml
[project]
name = "my-app"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.115",
    "pydantic>=2.9",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "ruff>=0.7",
    "pyright>=1.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project.scripts]
my-app = "my_app.cli:main"
```

### Sections explained

- **`[project]`** — PEP 621 metadata. Read by every modern tool. Runtime dependencies go here.
- **`[dependency-groups]`** — PEP 735 dev/test/docs dep buckets. Not shipped with published packages. `uv add --dev` writes here.
- **`[build-system]`** — How to build a wheel for distribution. For applications you don't publish, leave whatever `uv init` generated. For libraries, this is essential.
- **`[project.scripts]`** — Console-script entry points. Each line installs a CLI shim.
- **`[tool.<name>]`** — Per-tool config. Most modern tools (ruff, pyright, pytest, mypy, coverage, alembic) read their settings from here, replacing per-tool config files.

### Common `[tool.*]` sections

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "W"]

[tool.pyright]
strict = ["src"]
pythonVersion = "3.13"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

## Imports and `sys.path`

Python finds modules by searching `sys.path` — a list of directories. The first match wins.

The `src/` layout works because:
1. After `uv sync`, the project is installed in editable mode.
2. The installation puts the package on `sys.path`.
3. `import invoice_importer` finds it.

### Absolute vs. relative imports

```python
# Absolute (preferred for clarity)
from invoice_importer.domain.models import Invoice
from invoice_importer.storage import repository

# Relative (only inside packages)
from .models import Invoice              # same package
from ..storage import repository         # parent package
```

Use absolute imports unless you have a reason. Relative imports are useful inside large packages where the absolute path is verbose, or for portability when packages get renamed.

**Never use relative imports across major package boundaries.** Stay within one logical unit.

### `from __future__ import annotations`

Put this at the top of every Python file. It enables PEP 563 lazy annotation evaluation:

```python
from __future__ import annotations

# Now annotations are strings; forward references work without quotes
class Foo:
    bar: Bar    # works even though Bar isn't defined yet

class Bar:
    pass
```

Eliminates a whole category of NameError problems and is harmless in modern code.

## Tests

### Layout

```
tests/
├── conftest.py             # shared fixtures, importable across all tests
├── unit/                   # fast, no I/O
│   ├── test_domain.py
│   └── test_extraction.py
├── integration/            # real DB, real services
│   └── test_pipeline.py
└── e2e/                    # full stack via HTTP
    └── test_api.py
```

`conftest.py` is special: pytest auto-discovers it and shares its fixtures with all tests in the same directory and below. You can have one at the test root and additional ones in subdirectories for narrower scope.

### Why split unit / integration / e2e

- **Unit** runs in milliseconds — pure logic, no I/O. Should be 80% of your tests.
- **Integration** runs in seconds — real database, real PDF parsing, real LLM (mocked or not).
- **E2E** runs in tens of seconds — full HTTP stack, real DB, real services.

Pytest can mark and filter:

```python
import pytest

@pytest.mark.integration
async def test_real_db():
    ...
```

```toml
[tool.pytest.ini_options]
markers = [
    "integration: requires real DB",
    "e2e: requires full stack",
]
```

```powershell
uv run pytest tests/unit                 # fast loop during dev
uv run pytest -m "not integration"       # skip slow tests
uv run pytest                            # everything (CI)
```

### Test naming

- Files: `test_*.py`
- Classes (optional): `Test*`
- Functions: `test_*`

Pytest discovers everything matching this pattern automatically.

## Application-only conventions

### Configuration

Settings via environment variables, loaded with `pydantic-settings`:

```python
# src/my_app/config.py
from functools import lru_cache
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    database_url: str
    api_key: SecretStr
    log_level: str = "INFO"

@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

`.env` for local dev (gitignored), real env vars in production. `SecretStr` prevents accidental logging of credentials.

### Logging

Use stdlib `logging`, not `print`:

```python
import logging
logger = logging.getLogger(__name__)

logger.info("processing %s", filename)   # use %s, not f-string
```

`%s` formatting lets the framework skip the format step when the level is disabled. Configure logging at the entry point (`logging.basicConfig` in `main`).

### Layered architecture

For applications beyond trivial size:

```
src/<app>/
├── domain/         # core business models, no I/O
├── storage/        # database access
├── extraction/     # external integrations (LLMs, parsers)
├── sources/        # input sources (files, HTTP, queues)
├── api/            # web layer (routes, middleware)
└── cli.py          # alternate entry point
```

Rule: domain knows nothing about layers above it. Storage and extraction depend on domain. API depends on everything below it. This keeps the core testable in isolation.

## Library-only conventions

### Public API design

```python
# src/my_lib/__init__.py — your public surface
from my_lib.client import Client, ClientError
from my_lib.types import Result, Status

__all__ = ["Client", "ClientError", "Result", "Status"]
__version__ = "0.1.0"
```

Only export what you commit to maintaining. Internal modules use leading underscores: `_internal`, `_utils`.

### Type information

Modern libraries ship with type information:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/my_lib"]

# also include a marker:
```

```
src/my_lib/
├── __init__.py
├── py.typed              # empty file marking the package as typed
└── ...
```

The `py.typed` marker tells type checkers "this package has inline type annotations; trust them." Without it, pyright treats your library as `Any`.

### Documentation

Library authors typically use Sphinx or MkDocs. The choice is taste; both work.

## Quick decision tree

**One-off automation < 100 lines, no real deps?**
→ Single script with PEP 723 inline metadata.

**A program with structure but only consumed via CLI/HTTP?**
→ Application: `uv init --app --package`, `src/` layout, `[project.scripts]` for CLI.

**Code intended for `import` by other projects?**
→ Library: `uv init --lib`, careful public API in `__init__.py`, `py.typed` marker, semver discipline.

**Internal company tool with both CLI and importable bits?**
→ Application layout. Mark internal-but-importable parts clearly. If the importable surface grows, consider splitting into a separate library.

## File checklist for a new project

- [ ] `pyproject.toml` (created by `uv init`)
- [ ] `.python-version` (`uv python pin`)
- [ ] `uv.lock` (created by first `uv add`/`uv sync`)
- [ ] `.gitignore` with `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`, `*.egg-info/`
- [ ] `README.md`
- [ ] `src/<package>/__init__.py`
- [ ] `src/<package>/__main__.py` (if app)
- [ ] `tests/` with `conftest.py`
- [ ] `[tool.ruff]` and `[tool.pyright]` config in `pyproject.toml`
- [ ] `from __future__ import annotations` at the top of every module

## Anti-patterns

**Don't put runnable code at module top level.** Wrap it in `def main()` and gate with `if __name__ == "__main__":`. Otherwise, importing the module runs your code as a side effect.

**Don't use `pip` inside a `uv`-managed venv.** It bypasses the lockfile. Always `uv add`.

**Don't commit `.venv/`.** It's machine-specific and huge.

**Don't put dependencies in `setup.py` or `setup.cfg`.** These are legacy. Modern Python uses `pyproject.toml` exclusively.

**Don't put project code in the repo root without a `src/` directory.** It works at first, then breaks subtly when you try to install or distribute.

**Don't conflate `requirements.txt` with `pyproject.toml`.** `requirements.txt` is the legacy format; `pyproject.toml` is the modern one. uv uses neither for transitive locking — `uv.lock` is the lockfile. If you see `requirements.txt` in a modern project, it's probably exported for compatibility with non-uv tools.
