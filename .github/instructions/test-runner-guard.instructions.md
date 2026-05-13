---
applyTo: "finance-dashboard/tests/**/*.py"
description: "Use when editing pytest tests or nearby test helpers; run targeted pytest first, then full suite before finishing."
---
# Test Runner Guard

When you change files matched by applyTo, keep test feedback tight and deterministic.

## Run Order
1. Run the narrowest relevant test target first from the project folder:
   - `cd finance-dashboard`
   - `pytest tests/test_database.py -q` or `pytest tests/test_utils.py -q`
2. If targeted tests pass, run the full suite:
   - `pytest`
3. If failures are unrelated to the change, report them explicitly and do not hide them.

## Scope Notes
- Do not launch Streamlit for test-only tasks.
- Keep fixtures centralized in `tests/conftest.py`.
- For tests importing `app.py`, follow the streamlit-stubbing pattern used in `tests/test_utils.py`.
