# Finance Dashboard — Agent Instructions

Personal & Business Finance Dashboard built with **Streamlit + SQLite + Plotly**.  
All application code lives in `finance-dashboard/`.

## Run the App

```bash
cd finance-dashboard
pip install -r requirements.txt
streamlit run app.py
```

See [README](finance-dashboard/README.md) for deployment and cloud configuration.

## Run Tests

```bash
cd finance-dashboard
pytest
```

- Framework: **pytest** — config in [finance-dashboard/pytest.ini](finance-dashboard/pytest.ini)
- Test files live in [finance-dashboard/tests/](finance-dashboard/tests/)
- `conftest.py` provides `conn` (empty in-memory SQLite) and `conn_with_users` (with default users) fixtures
- `test_database.py` — auth, registration, `get_data`, `calculate_net_worth`
- `test_utils.py` — `convert_currency`, `format_currency`, `categorize_transaction`, `to_numeric_series`, `parse_mixed_date_series`
- `app.py` uses `st.*` at module level — tests stub the entire `streamlit` module via `sys.modules` in `test_utils.py` before importing `app`; follow this pattern for any new `app.py` tests

## Project Structure

| Path | Purpose |
|------|---------|
| [finance-dashboard/app.py](finance-dashboard/app.py) | Main Streamlit app — all UI pages, routing, CRUD forms, file parsing |
| [finance-dashboard/database.py](finance-dashboard/database.py) | SQLite helpers: connection, schema, CRUD, auth, import/export |
| [finance-dashboard/requirements.txt](finance-dashboard/requirements.txt) | Dependencies: streamlit, pandas, plotly, python-dotenv, openpyxl, xlrd, pdfplumber, pytest |
| [finance-dashboard/tests/](finance-dashboard/tests/) | pytest test suite |
| [finance-dashboard/_update_user.py](finance-dashboard/_update_user.py) | One-off admin script — not part of the app |

## Architecture Decisions

- **Single-file UI**: All Streamlit pages/tabs are in `app.py`. No multi-page folder structure.
- **SQLite (`finance.db`)**: Created at runtime. For cloud: set `DATABASE_URL` env var to a PostgreSQL/MySQL connection string.
- **Account types**: Every data table has `account_type` (`'personal'` or `'business'`) and `user_id` columns for multi-user isolation.
- **Currencies**: USD, EUR, INR stored as-is; converted at display time via `EXCHANGE_RATES` dict in `app.py`. Rates are hardcoded — not real-time.
- **Auth**: Login required before dashboard renders. Credentials from env vars or `.env` — **never hardcode passwords**.
- **CRUD pattern**: A `crud_configs` dict in `app.py` maps entry types to tables + field definitions; `st.data_editor()` drives grid-based edit/delete.

## UI Pages (sidebar navigation)

Overview · Income Tracking · Expenses Tracking · Investments · Fixed Deposits · Real Estate · Fund Allocation · Insights · Filters · Upload · Cash · Bank Statement Loading · Bank Insights

Auth pages (pre-login): Login · Create Account · Forgot Password (2-step wizard via `fp_step` session state)

## Database Tables

`income`, `expenses`, `investments`, `fixed_deposits`, `real_estate`, `cash`, `users`, `bank_statements`  
All data tables: `id, ..., currency, account_type, user_id`.

## Key Functions

**In `database.py`** — all DB access must go through these:

| Function | Purpose |
|----------|---------|
| `create_connection(db_file)` | SQLite connection with `PRAGMA busy_timeout = 30000` |
| `get_data(conn, table, date_filter, account_type, user_id)` | Filtered row fetch — always pass `account_type` + `user_id` |
| `calculate_net_worth(conn, account_type, user_id)` | Sum of investments + FDs + real estate + cash (USD-equivalent) |
| `calculate_income_expenses(conn, period, account_type, user_id)` | Returns `(income_usd, expenses_usd, savings_rate%)` |
| `authenticate_user(conn, username, password)` | Returns user dict or `None` |
| `register_user(conn, username, password, ...)` | Returns `(success: bool, error_msg: str)` |
| `import_excel_to_db(conn, excel_file, behavior)` | Bulk import; `behavior="append"` or `"replace"` |
| `save_bank_statement_rows(conn, bank_name, ...)` | Persist parsed bank statement; `replace_existing=True` deduplicates |

**In `app.py`** — utility helpers:

| Function | Purpose |
|----------|---------|
| `format_currency(amount, currency)` | Locale-aware currency string |
| `convert_currency(amount, from_cur, to_cur)` | Converts via USD using `EXCHANGE_RATES` |
| `parse_mixed_date_series(series)` | Tries day-first then month-first for mixed date formats |
| `to_numeric_series(series, ...)` | Strips non-numerics, handles DR/CR markers, parentheses |
| `normalize_bank_statement(df, mapping)` | Maps raw columns → `[date, description, income_amount, expense_amount, net_amount, transaction_type, category]` |
| `categorize_transaction(description)` | Regex-matches description against `category_map` |
| `maybe_rerun()` | Calls `st.rerun()` with legacy fallback — use instead of calling `st.rerun()` directly |

## Session State Keys

| Key | Type | Purpose |
|-----|------|---------|
| `logged_in` | bool | Authentication gate |
| `username` | str | Current user's username |
| `role` | str | `"admin"`, `"personal"`, or `"user"` |
| `user_id` | str | Set to `username` on login; used for data isolation |
| `selected_page` | str | Active sidebar navigation page |
| `fp_step` | int | Forgot-password wizard step (1 or 2) |
| `parsed_bank_statement_df` | DataFrame | Temp storage during multi-step bank statement import |

Admin role: sidebar shows "View Data As" dropdown to inspect any user's data.

## Environment Variables

Copy `.env.example` → `.env` (never commit `.env`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `finance.db` | SQLite path or cloud DB connection string |
| `ADMIN_PASSWORD` | `admin123` | Seeded on first run; change immediately |
| `PERSONAL_PASSWORD` | `personal123` | Seeded on first run |
| `BUSINESS_PASSWORD` | `business123` | Seeded on first run |

## Key Conventions

- All DB calls go through `database.py` — do not write raw SQL in `app.py`.
- Always pass `account_type` and `user_id` to `get_data()` for proper data isolation.
- Currency formatting uses `format_currency(amount, currency)` — not f-strings.
- Excel bulk upload expects sheets named exactly: `income`, `expenses`, `investments`, `fixed_deposits`, `real_estate`, `cash`.
- Bank statement column matching uses `BANK_COLUMN_ALIASES` dict — extend it there, not inline.

## Security Notes

- `.env` must be in `.gitignore` — never commit credentials.
- Passwords hashed with SHA-256 via `hash_password()` — never store plaintext.
- Parameterised queries throughout `database.py` — maintain this to prevent SQL injection.
- Security answers stored as lowercased SHA-256 hash.

## Critical Pitfalls

- **`PRAGMA busy_timeout = 30000`** is set in `create_connection()` — do not remove; prevents SQLite lock errors on Streamlit reruns.
- **Exchange rates are hardcoded** in three places: `EXCHANGE_RATES` in `app.py` (top-level constant) and inside `calculate_net_worth()` and `calculate_income_expenses()` in `database.py` — all three must be updated together when rates change. Last synced 2026-05-04 (EUR: 0.8537, INR: 95.11).
- **Workspace root has an empty `app.py`** — the actual Streamlit app entrypoint is `finance-dashboard/app.py`.
- **Streamlit reruns entire script** on any interaction — use `st.session_state` to preserve state; call `maybe_rerun()` instead of `st.rerun()` directly.
- **`finance.db` is local** — won't persist on stateless cloud hosts without `DATABASE_URL`.
- **Excel import stops on first sheet error** — user won't know which sheet failed; validate column names match expected schema before import.
- **PDF bank statement parsing** requires structured (text-layer) PDFs — image-based PDFs will silently fail via `extract_pdf_tables()`.
