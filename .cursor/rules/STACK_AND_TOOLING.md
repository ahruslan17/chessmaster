# Project Stack & Tooling Rules

This project follows a strict, modern Python tooling stack.
All code, dependencies, scripts, and workflows MUST comply with the rules below.

Deviation is allowed only if explicitly justified.

---

## 1. Python Version

- Use a single Python version defined in `pyproject.toml`
- Code must be compatible only with the declared version
- No backward-compatibility hacks

---

## 2. Dependency Management — UV (MANDATORY)

UV is the **only** allowed tool for:
- dependency installation
- dependency resolution
- virtual environment management
- script execution

Forbidden:
- pip
- poetry
- pipenv
- pip-tools
- manual virtualenv usage

### Allowed commands

```bash
uv add <package>
uv remove <package>
uv sync
uv lock
uv run <command>
```

### Rules

* All dependencies must be declared in `pyproject.toml`
* Lockfile (`uv.lock`) must be committed
* No implicit dependencies
* Dev dependencies must be separated from runtime dependencies

---

## 3. Project Structure — SRC Layout (MANDATORY)

All Python source code must live inside `src/`.

```text
.
├── src/
│   └── app/
│       ├── __init__.py
│       ├── core/
│       ├── models/
│       ├── services/
│       ├── api/
│       └── utils/
├── tests/
├── alembic/
│   └── versions/
├── pyproject.toml
├── uv.lock
```

### Rules

* No imports from project root
* All imports must resolve via `src`
* Tests must import code exactly as production code does

---

## 4. Linting & Formatting — Ruff (MANDATORY)

Ruff is the **single source of truth** for:

* linting
* formatting
* import sorting
* code quality rules

### Rules

* All Ruff checks must pass
* No ignored rules without justification
* `# noqa` allowed only with explicit reason

Example:

```python
# noqa: PLR0913  # acceptable due to external API contract
```

---

## 5. Static Analysis & Coverage — Sonar (MANDATORY)

Sonar is used for:

* code quality analysis
* technical debt tracking
* test coverage validation

### Requirements

* No critical or major issues
* All new code must be covered by tests
* Coverage must not decrease
* Code smells must be fixed or justified

---

## 6. Testing

### Test Framework

* pytest only

### Rules

* Tests required for all new logic
* Edge cases must be covered
* External dependencies must be mocked
* Tests must be runnable via:

```bash
uv run pytest --cov=src
```

---

## 7. Database & Migrations — Alembic (If DB Exists)

If the project uses a database:

* Alembic is mandatory
* All schema changes must go through migrations

### Rules

* No manual schema changes
* No edited migration history
* Migrations must be deterministic

```bash
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

---

## 8. CI / Quality Gates

Before merge, the following must pass:

* Ruff
* Tests
* Coverage
* Sonar quality gates

Broken main branch is unacceptable.
