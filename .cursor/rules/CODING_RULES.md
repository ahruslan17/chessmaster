# Coding Rules & Style Guide

This document defines how code MUST be written in this project.
Focus: readability, predictability, maintainability.

---

## 1. General Principles

- Code is written for humans first
- Explicit > implicit
- Simple > clever
- Readability > performance (until proven otherwise)

Avoid:
- magic values
- hidden side effects
- implicit global state

---

## 2. Type Hints (MANDATORY)

- All public functions and methods MUST be typed
- Prefer precise types over `Any`
- Use `from __future__ import annotations`

```python
def calculate_score(user_id: int, weights: dict[str, float]) -> float:
    ...
```

---

## 3. Naming Rules

### Variables & Functions

* snake_case
* descriptive, no abbreviations

Bad: `cnt`, `tmp`, `val`
Good: `user_count`, `temporary_path`, `score_value`

### Classes

* PascalCase
* nouns, not verbs

### Constants

* UPPER_CASE

---

## 4. Functions

### Rules

* One function = one responsibility
* Prefer small functions (≤ 30 lines)
* Avoid deeply nested logic
* No hidden mutations

Bad:

```python
def process():
    ...
```

Good:

```python
def validate_input(...)
def transform_data(...)
def persist_result(...)
```

---

## 5. Imports

* Absolute imports only
* Grouped and ordered

```python
import logging
from typing import Iterable

import numpy as np

from app.services.scoring import calculate_score
```

---

## 6. Error Handling

* Never silently ignore errors
* Catch only specific exceptions
* Add context when re-raising

```python
try:
    result = parse_payload(data)
except ValueError as exc:
    raise InvalidPayloadError("Invalid user payload") from exc
```

---

## 7. Logging

* Use `logging`, not `print`
* No logging in tight loops without reason
* Log business events, not implementation details

---

## 8. Tests

### Rules

* Test behavior, not implementation
* One logical assertion per test when possible
* Clear test names

```python
def test_user_is_blocked_when_balance_negative():
    ...
```

---

## 9. Code Changes Policy (Cursor-specific)

When modifying existing code:

* Do NOT rewrite entire files
* Make minimal, focused diffs
* Preserve existing behavior unless explicitly requested
* Explain reasoning before applying changes

---

## 10. Documentation

* Public functions must have docstrings
* Complex logic must be commented
* Comments explain **why**, not **what**

---

## 11. Forbidden Practices

* Global mutable state
* Monkey patching
* Hardcoded secrets
* Hidden side effects in constructors
* Overusing `Any`

---

## 12. Final Rule

If unsure:

> Write code that a new senior engineer can understand in 30 seconds.
