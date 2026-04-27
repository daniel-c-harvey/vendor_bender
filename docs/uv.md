# `uv` Cheatsheet

Quick reference for `uv` — Python package, project, and environment manager. Drop-in replacement for pip, pip-tools, pipx, virtualenv, and pyenv.

## Mental model

`uv` manages three things:
1. **Python interpreters** (cached per-version, installed on demand)
2. **Virtual environments** (`.venv/` per project, gitignored)
3. **Dependencies** (declared in `pyproject.toml`, locked in `uv.lock`)

Every `uv` command auto-syncs `.venv/` against `uv.lock` before doing its work. You rarely need to think about activation state.

## File layout

| File | Role | Commit? |
|---|---|---|
| `pyproject.toml` | Project metadata, declared deps | Yes |
| `uv.lock` | Resolved exact versions of all transitive deps | Yes |
| `.python-version` | Pinned Python version for this project | Yes |
| `.venv/` | The actual virtual environment | **No** (gitignore) |

## Project lifecycle

### Bootstrap a new project

```powershell
uv init --package my-tool        # creates src/ layout with proper package
uv init --lib my-lib             # for libraries
uv init --app my-app             # for applications (default)
```

Creates `pyproject.toml`, `.python-version`, `src/<package>/`, `README.md`, `.gitignore`. Run once per project.

### Pin a Python version

```powershell
uv python install 3.13           # download & cache an interpreter
uv python pin 3.13               # write .python-version
uv python list                   # see all available versions
uv python list --only-installed  # see what's locally cached
```

`.python-version` is read by `uv` (and `pyenv`, if installed). Commit it.

## Day-to-day commands

### The big three

```powershell
uv run <cmd>                     # run a command in the project's venv
uv add <pkg>                     # add a runtime dependency
uv sync                          # ensure venv matches lockfile
```

Internalize these. Everything else is occasional.

### Adding and removing dependencies

```powershell
uv add fastapi                              # single package
uv add fastapi sqlalchemy pydantic          # multiple
uv add 'fastapi>=0.115'                     # with version constraint
uv add 'sqlalchemy[asyncio]'                # with extras (always quote on PowerShell)

uv add --dev pytest pytest-asyncio          # dev-only dependency
uv add --dev ruff pyright aiosqlite

uv remove some-package                      # remove
uv remove --dev pytest-mock                 # remove dev dep
```

`uv add` updates `pyproject.toml`, re-resolves the dep graph, updates `uv.lock`, and installs into `.venv/` — all in one shot. You almost never edit dependency lists by hand.

**PowerShell quoting rules:**
- Quote anything with `[` `]` (extras): `'sqlalchemy[asyncio]'`
- Quote anything with `>` `<` `=` (version specs): `'fastapi>=0.115'`

### Running things

```powershell
uv run python script.py
uv run python -m invoice_importer
uv run pytest
uv run ruff check .
uv run pyright
uv run alembic upgrade head
uv run uvicorn app:app --reload

uv run --with httpie http GET https://example.com   # run with a temporary extra dep
```

`uv run` resolves the venv state before executing — fast if already in sync.

### Syncing the venv

```powershell
uv sync                          # update venv to match lockfile
uv sync --frozen                 # fail if pyproject.toml requires re-locking (CI)
uv sync --no-dev                 # exclude dev dependencies (production install)
```

Run `uv sync` after `git pull` if a teammate added dependencies. Use `--frozen` in CI to catch lockfile drift.

### Upgrading

```powershell
uv lock                          # re-resolve, keep existing pins where possible
uv lock --upgrade                # bump everything within constraints
uv lock --upgrade-package fastapi   # bump just one
```

After `uv lock --upgrade`, run tests and review `git diff uv.lock` before committing.

## Inspection

```powershell
uv tree                          # full dependency tree
uv tree --depth 1                # direct deps only
uv tree --package fastapi        # show ancestors of a package

uv pip list                      # what's actually installed in .venv
uv pip show fastapi              # detailed package info
```

## Global tools (CLIs)

For tools you want available system-wide but isolated from project deps:

```powershell
uv tool install ruff             # install globally, isolated venv
uv tool install black

uv tool list
uv tool upgrade ruff
uv tool upgrade --all
uv tool uninstall black

uvx <tool> [args]                # one-off run, no install (like npx)
uvx ruff check .
uvx cookiecutter https://github.com/some/template
```

Replaces `pipx` and `npm install -g`.

## Manual venv operations (rare)

```powershell
uv venv                          # create .venv explicitly
uv venv --python 3.12            # specify interpreter
uv venv .venv-other              # custom location
```

Activation (if you want a long-lived shell session in the venv):

```powershell
# PowerShell
.\.venv\Scripts\Activate.ps1

# bash/zsh
source .venv/bin/activate

# any shell, after activation
deactivate
```

`uv run` makes this mostly unnecessary, but PyCharm and other IDEs activate automatically.

## Cache

```powershell
uv cache clean                   # clear uv's package cache (rarely needed)
uv cache dir                     # show cache location
```

## CI shape

```yaml
- uses: astral-sh/setup-uv@v4
- run: uv sync --frozen          # fail if lockfile out of date
- run: uv run ruff check .
- run: uv run pyright
- run: uv run pytest
```

`--frozen` is the key flag. It guarantees CI runs against exactly the locked versions.

## Common workflows

### Starting a new project

```powershell
mkdir my-tool && cd my-tool
uv init --package
uv python pin 3.13
uv add fastapi sqlalchemy pydantic
uv add --dev pytest ruff pyright
uv run pytest
```

### Joining an existing project

```powershell
git clone <repo> && cd <repo>
uv sync                          # creates .venv/, installs everything from uv.lock
uv run pytest                    # verify the toolchain works
```

### Daily inner loop

```powershell
uv run python -m my_tool         # run the app
uv run pytest                    # tests
uv run ruff check .              # lint
uv run pyright                   # type-check
```

### Adding a dep mid-project

```powershell
uv add httpx                     # adds, locks, installs
git diff pyproject.toml uv.lock  # review what changed
```

### Pulling teammate changes

```powershell
git pull
uv sync                          # catch up to their lockfile
```

### Periodic dep maintenance

```powershell
uv lock --upgrade                # bump all to latest allowed
uv run pytest                    # verify
git diff uv.lock                 # review
git commit -am "bump deps"
```

## Quick reference table

| Command | Frequency | What it does |
|---|---|---|
| `uv run <cmd>` | constantly | Run command in project venv |
| `uv add <pkg>` | weekly | Add runtime dep |
| `uv add --dev <pkg>` | occasional | Add dev dep |
| `uv remove <pkg>` | occasional | Remove dep |
| `uv sync` | after pull | Match venv to lockfile |
| `uv sync --frozen` | CI | Fail if lockfile stale |
| `uv lock --upgrade` | monthly | Bump pinned versions |
| `uv tree` | debugging | Show dep graph |
| `uv pip list` | debugging | What's installed |
| `uv tool install <cli>` | rarely | Install global CLI |
| `uvx <cli>` | occasionally | One-off CLI run |
| `uv init` | once per project | Bootstrap |
| `uv python install <ver>` | per new Python | Install interpreter |
| `uv python pin <ver>` | once per project | Pin interpreter version |

## npm parallels (for reference)

| npm | uv |
|---|---|
| `package.json` | `pyproject.toml` |
| `package-lock.json` | `uv.lock` |
| `node_modules/` | `.venv/` |
| `.nvmrc` | `.python-version` |
| `npm install` | `uv sync` |
| `npm ci` | `uv sync --frozen` |
| `npm install <pkg>` | `uv add <pkg>` |
| `npm install --save-dev <pkg>` | `uv add --dev <pkg>` |
| `npm uninstall <pkg>` | `uv remove <pkg>` |
| `npm update` | `uv lock --upgrade` |
| `npm ls` | `uv tree` |
| `npm install -g <pkg>` | `uv tool install <pkg>` |
| `npx <cmd>` | `uvx <cmd>` |
| `npm run <script>` | `uv run <cmd>` (no scripts section needed) |

## Gotchas

**PowerShell needs quotes around `[extras]` and version constraints.** `uv add sqlalchemy[asyncio]` fails; `uv add 'sqlalchemy[asyncio]'` works.

**Don't `pip install` into a uv-managed venv.** It bypasses `uv` entirely — `pyproject.toml` and `uv.lock` won't update. Always `uv add`.

**PyCharm's "Add package" UI uses pip by default.** Same problem as above. Use the terminal: `uv add <pkg>`. PyCharm picks up the changes automatically.

**`.venv/` should never be committed.** Add it to `.gitignore` (uv's `init` does this for you).

**`--frozen` in CI is non-negotiable.** Without it, you can ship code that doesn't match the lockfile.
