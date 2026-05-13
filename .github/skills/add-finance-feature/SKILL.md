---
name: add-finance-feature
description: "Use when adding a new finance tracking feature end-to-end in finance-dashboard: schema, CRUD wiring, views, and tests."
---
# Add Finance Feature Skill

Use this workflow when introducing a new tracked domain (for example liabilities or insurance) in the Finance Dashboard.

## Inputs
- Feature name and user-facing label
- Required fields and data types
- Pages where the data should appear
- Whether it contributes to net worth or income/expense calculations

## Workflow
1. Database design in `finance-dashboard/database.py`:
   - Add table creation SQL in `create_tables`.
   - Include `account_type` and `user_id` for data isolation.
   - Add helper methods only in `database.py` (no raw SQL in UI file).
2. App wiring in `finance-dashboard/app.py`:
   - Add CRUD config entry and form fields.
   - Ensure data fetches pass `account_type` and `user_id`.
   - Use `format_currency` and `convert_currency` for display/rollups.
3. Calculations and metrics:
   - If feature affects totals, update `calculate_net_worth` and/or `calculate_income_expenses` in `database.py`.
   - If exchange rates are touched, keep all three hardcoded rate locations in sync.
4. Tests in `finance-dashboard/tests/`:
   - Add unit tests for new DB helper and data filtering behavior.
   - For any tests importing `app.py`, stub streamlit as shown in `tests/test_utils.py`.
5. Validation:
   - Run targeted tests first, then `pytest` full suite.

## Done Checklist
- Table includes `currency`, `account_type`, and `user_id` where applicable.
- No SQL added to UI layer.
- New UI paths respect session state and current user scope.
- Tests cover happy path and at least one filter/isolation case.
