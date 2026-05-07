import io
import os
import sqlite3
import hashlib
import re
import time
import pandas as pd
from datetime import datetime

# SQLAlchemy is used when DATABASE_URL points to PostgreSQL (cloud deployments).
# For local SQLite usage the standard sqlite3 module is used directly.
try:
    from sqlalchemy import create_engine, text as sa_text
    _SQLALCHEMY_AVAILABLE = True
except ImportError:
    _SQLALCHEMY_AVAILABLE = False


_LAST_CONNECTION_ERROR = None


def _set_last_connection_error(err):
    global _LAST_CONNECTION_ERROR
    _LAST_CONNECTION_ERROR = _sanitize_connection_error(err)


def _sanitize_connection_error(err):
    if err is None:
        return None
    msg = str(err)
    # Redact credentials that may appear in URLs.
    return re.sub(r"://([^:@/]+):([^@/]+)@", r"://\1:***@", msg)


def get_last_connection_error():
    return _LAST_CONNECTION_ERROR


def safe_error_message(err):
    return _sanitize_connection_error(err)


def _query_debug_enabled():
    return str(os.getenv("DB_QUERY_LOG", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _slow_query_threshold_ms():
    raw = str(os.getenv("DB_SLOW_QUERY_MS", "250")).strip()
    try:
        return max(1.0, float(raw))
    except Exception:
        return 250.0


def _normalize_sql_for_log(sql):
    return " ".join(str(sql).split())[:220]


def _log_query_timing(sql, elapsed_ms, rowcount=None):
    if not _query_debug_enabled():
        return
    level = "SLOW" if elapsed_ms >= _slow_query_threshold_ms() else "FAST"
    row_info = "" if rowcount is None else f" rows={rowcount}"
    print(f"DB_QUERY [{level}] {elapsed_ms:.1f}ms{row_info} sql={_normalize_sql_for_log(sql)}")


class _PgConnection:
    """Thin wrapper that makes a SQLAlchemy engine behave like a sqlite3 connection
    for the limited subset of operations used in this codebase:
      conn.execute(sql, params)  -> executes a single parameterised statement
      conn.executemany(sql, rows)
      conn.commit()              -> no-op (autocommit via begin())
      pd.read_sql_query(sql, conn, params=...)  -> works natively with engine
    """

    def __init__(self, engine):
        self._engine = engine

    # Allow pd.read_sql_query to use this object directly as a connection
    def __enter__(self): return self
    def __exit__(self, *a): pass

    # Make pandas happy — it checks for a 'cursor' or uses the object as a DBAPI conn
    @property
    def _engine_ref(self):
        return self._engine

    def execute(self, sql, params=None):
        # Convert SQLite-style ? placeholders to :p0, :p1, … for SQLAlchemy
        bound_sql, bound_params = _adapt_sql(sql, params)
        start = time.perf_counter()
        with self._engine.begin() as c:
            result = c.execute(sa_text(bound_sql), bound_params or {})
        elapsed_ms = (time.perf_counter() - start) * 1000
        _log_query_timing(sql, elapsed_ms, result.rowcount)

    def executemany(self, sql, rows):
        if not rows:
            return
        bound_sql, _ = _adapt_sql(sql, rows[0])
        batch_params = []
        for row in rows:
            _, bound_params = _adapt_sql(sql, row)
            batch_params.append(bound_params)
        start = time.perf_counter()
        with self._engine.begin() as c:
            # Execute as a single batch to reduce network round trips on hosted Postgres.
            result = c.execute(sa_text(bound_sql), batch_params)
        elapsed_ms = (time.perf_counter() - start) * 1000
        _log_query_timing(sql, elapsed_ms, result.rowcount)

    def commit(self):
        pass  # SQLAlchemy uses autocommit inside begin() blocks

    def cursor(self):
        return _PgCursor(self._engine)

    def close(self):
        self._engine.dispose()


class _PgCursor:
    """Minimal cursor-like wrapper for operations that use cursor.execute + rowcount."""

    def __init__(self, engine):
        self._engine = engine
        self.rowcount = 0

    def execute(self, sql, params=None):
        bound_sql, bound_params = _adapt_sql(sql, params)
        start = time.perf_counter()
        with self._engine.begin() as c:
            result = c.execute(sa_text(bound_sql), bound_params or {})
            self.rowcount = result.rowcount
        elapsed_ms = (time.perf_counter() - start) * 1000
        _log_query_timing(sql, elapsed_ms, self.rowcount)


def _adapt_sql(sql, params):
    """Convert SQLite ? placeholders and INSERT OR IGNORE to PostgreSQL syntax."""
    # INSERT OR IGNORE -> INSERT ... ON CONFLICT DO NOTHING
    adapted = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO").replace(
        "INSERT OR IGNORE", "INSERT"
    )
    if "INSERT INTO" in adapted and "ON CONFLICT" not in adapted and "OR IGNORE" not in sql:
        pass  # normal insert
    elif "INSERT OR IGNORE" in sql:
        adapted = adapted.rstrip().rstrip(")") + ") ON CONFLICT DO NOTHING"

    if not params:
        return adapted, {}

    items = list(params)
    bound = {}
    idx = 0
    result = []
    i = 0
    while i < len(adapted):
        if adapted[i] == '?' and idx < len(items):
            key = f"p{idx}"
            bound[key] = items[idx]
            result.append(f":{key}")
            idx += 1
        else:
            result.append(adapted[i])
        i += 1
    return "".join(result), bound


def create_connection(db_file):
    """Return a connection for either SQLite (local) or PostgreSQL (cloud).

    When db_file looks like a PostgreSQL URL (starts with 'postgres') and
    SQLAlchemy is available, returns a _PgConnection wrapping a SQLAlchemy engine.
    Otherwise falls back to a plain sqlite3 connection.
    """
    _set_last_connection_error(None)

    # PostgreSQL path
    if _SQLALCHEMY_AVAILABLE and db_file and db_file.startswith("postgres"):
        # Streamlit Cloud sets DATABASE_URL as postgres://… but SQLAlchemy 2.x
        # requires postgresql://…
        url = db_file.replace("postgres://", "postgresql://", 1)
        try:
            engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
            # Validate credentials/network early so app can render a clear message.
            with engine.connect() as c:
                c.execute(sa_text("SELECT 1"))
            return _PgConnection(engine)
        except Exception as e:
            _set_last_connection_error(e)
            print(f"PostgreSQL connection failed: {e}")
            try:
                engine.dispose()
            except Exception:
                pass
            return None
    elif db_file and db_file.startswith("postgres") and not _SQLALCHEMY_AVAILABLE:
        _set_last_connection_error("SQLAlchemy is not installed in this environment")
        return None

    # SQLite path (default)
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        conn.execute("PRAGMA busy_timeout = 30000")
    except sqlite3.Error as e:
        _set_last_connection_error(e)
        print(e)
    return conn


def _is_postgres(conn):
    """Return True when conn is a PostgreSQL (_PgConnection) connection."""
    return isinstance(conn, _PgConnection)


def _pk(conn):
    """Return the correct auto-increment primary key DDL for this connection type."""
    return "SERIAL PRIMARY KEY" if _is_postgres(conn) else "INTEGER PRIMARY KEY"


def db_read_sql(sql, conn, params=None):
    """Execute a SELECT query and return a DataFrame.

    Works with both a sqlite3 connection (params as tuple) and a _PgConnection
    (converts ? placeholders to :pN named params for SQLAlchemy).
    """
    if _is_postgres(conn):
        adapted_sql, bound_params = _adapt_sql(sql, params)
        start = time.perf_counter()
        with conn._engine.connect() as c:
            df = pd.read_sql_query(sa_text(adapted_sql), c,
                                   params=bound_params if bound_params else None)
        elapsed_ms = (time.perf_counter() - start) * 1000
        _log_query_timing(sql, elapsed_ms, len(df.index))
        return df
    start = time.perf_counter()
    df = pd.read_sql_query(sql, conn, params=params)
    elapsed_ms = (time.perf_counter() - start) * 1000
    _log_query_timing(sql, elapsed_ms, len(df.index))
    return df


def create_tables(conn):
    pk = _pk(conn)
    sql_create_income_table = f"""
    CREATE TABLE IF NOT EXISTS income (
        id {pk},
        source TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        date TEXT NOT NULL,
        type TEXT NOT NULL,
        account_type TEXT DEFAULT 'personal',
        user_id TEXT DEFAULT NULL
    );
    """
    sql_create_expenses_table = f"""
    CREATE TABLE IF NOT EXISTS expenses (
        id {pk},
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        date TEXT NOT NULL,
        account_type TEXT DEFAULT 'personal',
        user_id TEXT DEFAULT NULL
    );
    """
    sql_create_investments_table = f"""
    CREATE TABLE IF NOT EXISTS investments (
        id {pk},
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        invested_amount REAL NOT NULL,
        current_value REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        date_purchased TEXT NOT NULL,
        account_type TEXT DEFAULT 'personal',
        user_id TEXT DEFAULT NULL
    );
    """
    sql_create_fixed_deposits_table = f"""
    CREATE TABLE IF NOT EXISTS fixed_deposits (
        id {pk},
        bank TEXT NOT NULL,
        principal REAL NOT NULL,
        interest_rate REAL NOT NULL,
        maturity_date TEXT NOT NULL,
        maturity_value REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        account_type TEXT DEFAULT 'personal',
        user_id TEXT DEFAULT NULL
    );
    """
    sql_create_real_estate_table = f"""
    CREATE TABLE IF NOT EXISTS real_estate (
        id {pk},
        property_name TEXT NOT NULL,
        purchase_price REAL NOT NULL,
        current_value REAL NOT NULL,
        rental_income REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        account_type TEXT DEFAULT 'personal',
        user_id TEXT DEFAULT NULL
    );
    """
    sql_create_cash_table = f"""
    CREATE TABLE IF NOT EXISTS cash (
        id {pk},
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        date TEXT NOT NULL,
        account_type TEXT DEFAULT 'personal',
        user_id TEXT DEFAULT NULL
    );
    """
    sql_create_bank_statements_table = f"""
    CREATE TABLE IF NOT EXISTS bank_statements (
        id {pk},
        bank_name TEXT NOT NULL,
        txn_date TEXT NOT NULL,
        description TEXT,
        category TEXT,
        income_amount REAL DEFAULT 0,
        expense_amount REAL DEFAULT 0,
        net_amount REAL DEFAULT 0,
        currency TEXT DEFAULT 'USD',
        source_name TEXT,
        account_type TEXT DEFAULT 'personal',
        created_at TEXT NOT NULL,
        user_id TEXT DEFAULT NULL
    );
    """
    sql_create_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_income_user_account_date ON income(user_id, account_type, date)",
        "CREATE INDEX IF NOT EXISTS idx_income_user_account_currency ON income(user_id, account_type, currency)",
        "CREATE INDEX IF NOT EXISTS idx_expenses_user_account_date ON expenses(user_id, account_type, date)",
        "CREATE INDEX IF NOT EXISTS idx_expenses_user_account_currency ON expenses(user_id, account_type, currency)",
        "CREATE INDEX IF NOT EXISTS idx_investments_user_account ON investments(user_id, account_type)",
        "CREATE INDEX IF NOT EXISTS idx_investments_user_account_currency ON investments(user_id, account_type, currency)",
        "CREATE INDEX IF NOT EXISTS idx_fixed_deposits_user_account ON fixed_deposits(user_id, account_type)",
        "CREATE INDEX IF NOT EXISTS idx_fixed_deposits_user_account_currency ON fixed_deposits(user_id, account_type, currency)",
        "CREATE INDEX IF NOT EXISTS idx_real_estate_user_account ON real_estate(user_id, account_type)",
        "CREATE INDEX IF NOT EXISTS idx_real_estate_user_account_currency ON real_estate(user_id, account_type, currency)",
        "CREATE INDEX IF NOT EXISTS idx_cash_user_account_date ON cash(user_id, account_type, date)",
        "CREATE INDEX IF NOT EXISTS idx_cash_user_account_currency ON cash(user_id, account_type, currency)",
        "CREATE INDEX IF NOT EXISTS idx_bank_statements_user_account_date ON bank_statements(user_id, account_type, txn_date)",
        "CREATE INDEX IF NOT EXISTS idx_bank_statements_user_account_bank ON bank_statements(user_id, account_type, bank_name)",
        "CREATE INDEX IF NOT EXISTS idx_bank_statements_user_account_sort ON bank_statements(user_id, account_type, txn_date, id)",
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
    ]
    try:
        c = conn.cursor()
        c.execute(sql_create_income_table)
        c.execute(sql_create_expenses_table)
        c.execute(sql_create_investments_table)
        c.execute(sql_create_fixed_deposits_table)
        c.execute(sql_create_real_estate_table)
        c.execute(sql_create_cash_table)
        c.execute(sql_create_bank_statements_table)
        for idx_sql in sql_create_indexes:
            c.execute(idx_sql)
        conn.commit()
    except Exception as e:
        print(e)


def migrate_add_user_id(conn):
    """Safely add user_id column to all existing tables (no-op if already present)."""
    tables = ['income', 'expenses', 'investments', 'fixed_deposits', 'real_estate', 'cash', 'bank_statements']
    for table in tables:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT DEFAULT NULL")
            conn.commit()
        except Exception:
            pass  # Column already exists


def get_all_usernames(conn):
    df = db_read_sql("SELECT username FROM users ORDER BY username", conn)
    return df['username'].tolist()


def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def verify_password(password, password_hash):
    return hash_password(password) == password_hash


def create_users_table(conn):
    pk = _pk(conn)
    sql_create_users_table = f"""
    CREATE TABLE IF NOT EXISTS users (
        id {pk},
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'user',
        first_name TEXT DEFAULT '',
        last_name TEXT DEFAULT '',
        date_of_birth TEXT DEFAULT '',
        email TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        country TEXT DEFAULT '',
        security_question TEXT DEFAULT '',
        security_answer_hash TEXT DEFAULT ''
    );
    """
    try:
        c = conn.cursor()
        c.execute(sql_create_users_table)
        conn.commit()
    except Exception as e:
        print(e)
    # Migrate existing tables that lack the new columns
    new_cols = [
        ("first_name", "TEXT DEFAULT ''"),
        ("last_name", "TEXT DEFAULT ''"),
        ("date_of_birth", "TEXT DEFAULT ''"),
        ("email", "TEXT DEFAULT ''"),
        ("phone", "TEXT DEFAULT ''"),
        ("country", "TEXT DEFAULT ''"),
        ("security_question", "TEXT DEFAULT ''"),
        ("security_answer_hash", "TEXT DEFAULT ''"),
    ]
    for col, col_type in new_cols:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            conn.commit()
        except Exception:
            pass  # Column already exists


def get_user(conn, username):
    query = "SELECT * FROM users WHERE username = ?"
    df = db_read_sql(query, conn, params=(username,))
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def get_env_password(username, default_password):
    env_key = f"{username.upper()}_PASSWORD"
    return os.getenv(env_key, default_password)


def insert_default_users(conn):
    default_users = [
        ('admin', hash_password(get_env_password('admin', 'admin123')), 'admin'),
        ('personal', hash_password(get_env_password('personal', 'personal123')), 'personal'),
        ('business', hash_password(get_env_password('business', 'business123')), 'business')
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        default_users
    )
    conn.commit()


def authenticate_user(conn, username, password):
    user = get_user(conn, username)
    if user and verify_password(password, user['password_hash']):
        return user
    return None


def register_user(conn, username, password, first_name='', last_name='',
                  date_of_birth='', email='', phone='', country='',
                  security_question='', security_answer=''):
    """Create a new user account with role 'user'.
    Returns (True, '') on success or (False, error_message) on failure."""
    if not username or not password:
        return False, "Username and password are required."
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if not first_name.strip():
        return False, "First name is required."
    if not last_name.strip():
        return False, "Last name is required."
    if not email.strip() or '@' not in email:
        return False, "A valid email address is required."
    if not security_question or not security_answer.strip():
        return False, "Security question and answer are required for password recovery."
    existing = get_user(conn, username)
    if existing:
        return False, f"Username '{username}' is already taken."
    try:
        conn.execute(
            """INSERT INTO users
               (username, password_hash, role, first_name, last_name,
                date_of_birth, email, phone, country,
                security_question, security_answer_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                username.strip(), hash_password(password), 'user',
                first_name.strip(), last_name.strip(),
                date_of_birth, email.strip().lower(), phone.strip(), country.strip(),
                security_question, hash_password(security_answer.strip().lower())
            )
        )
        conn.commit()
        return True, ""
    except Exception as e:
        return False, str(e)


def get_user_by_email(conn, email):
    """Return user dict by email, or None."""
    df = db_read_sql("SELECT * FROM users WHERE email = ?", conn,
                     params=(email.strip().lower(),))
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def verify_security_answer(conn, username, answer):
    """Return True if the supplied answer matches the stored hash."""
    user = get_user(conn, username)
    if not user or not user.get('security_answer_hash'):
        return False
    return verify_password(answer.strip().lower(), user['security_answer_hash'])


def reset_user_password(conn, username, new_password):
    """Update the password for an existing user."""
    conn.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                 (hash_password(new_password), username))
    conn.commit()


def update_user_profile(conn, username, first_name, last_name, date_of_birth,
                        email, phone='', country='', security_question='',
                        security_answer=''):
    """Update profile details for an existing user.
    Returns (True, '') on success or (False, error_message) on failure."""
    if not first_name.strip():
        return False, "First name is required."
    if not last_name.strip():
        return False, "Last name is required."
    if not email.strip() or '@' not in email:
        return False, "A valid email address is required."

    user = get_user(conn, username)
    if not user:
        return False, "User not found."

    try:
        if security_answer.strip():
            conn.execute(
                """UPDATE users
                   SET first_name = ?, last_name = ?, date_of_birth = ?,
                       email = ?, phone = ?, country = ?,
                       security_question = ?, security_answer_hash = ?
                   WHERE username = ?""",
                (
                    first_name.strip(), last_name.strip(), str(date_of_birth),
                    email.strip().lower(), phone.strip(), country.strip(),
                    security_question, hash_password(security_answer.strip().lower()),
                    username,
                )
            )
        else:
            conn.execute(
                """UPDATE users
                   SET first_name = ?, last_name = ?, date_of_birth = ?,
                       email = ?, phone = ?, country = ?,
                       security_question = ?
                   WHERE username = ?""",
                (
                    first_name.strip(), last_name.strip(), str(date_of_birth),
                    email.strip().lower(), phone.strip(), country.strip(),
                    security_question, username,
                )
            )
        conn.commit()
        return True, ""
    except sqlite3.Error as e:
        return False, str(e)


def import_excel_to_db(conn, excel_file, behavior="append", user_id=None):
    expected_sheets = {
        "income": ["source", "amount", "currency", "date", "type", "account_type"],
        "expenses": ["category", "amount", "currency", "date", "account_type"],
        "investments": ["category", "name", "invested_amount", "current_value", "currency", "date_purchased", "account_type"],
        "fixed_deposits": ["bank", "principal", "interest_rate", "maturity_date", "maturity_value", "currency", "account_type"],
        "real_estate": ["property_name", "purchase_price", "current_value", "rental_income", "currency", "account_type"],
        "cash": ["amount", "currency", "date", "account_type"]
    }

    try:
        workbook = pd.read_excel(excel_file, sheet_name=None)
    except Exception as e:
        raise ValueError(f"Unable to read Excel file: {e}")

    inserted = []
    for table_name, required_cols in expected_sheets.items():
        if table_name not in workbook:
            continue

        df = workbook[table_name].copy()
        if df.empty:
            continue

        missing_columns = [col for col in required_cols if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Sheet '{table_name}' is missing required columns: {', '.join(missing_columns)}")

        df = df[required_cols].copy()
        if "account_type" not in df.columns:
            df["account_type"] = "personal"

        # Always stamp the importing user's id so the rows are visible to them
        df["user_id"] = user_id

        insert_cols = required_cols + ["user_id"]

        if behavior == "replace":
            if user_id:
                conn.execute(f"DELETE FROM {table_name} WHERE user_id = ?", (user_id,))
            else:
                conn.execute(f"DELETE FROM {table_name}")

        placeholders = ",".join(["?" for _ in insert_cols])
        insert_sql = f"INSERT INTO {table_name} ({', '.join(insert_cols)}) VALUES ({placeholders})"
        records = [tuple(row[col] for col in insert_cols) for _, row in df.iterrows()]

        if records:
            conn.executemany(insert_sql, records)
            inserted.append((table_name, len(records)))

    if not inserted:
        raise ValueError("No supported sheets were found in the uploaded workbook.")

    conn.commit()
    return inserted


def export_db_to_excel(conn, account_type=None, user_id=None):
    tables = [
        "income",
        "expenses",
        "investments",
        "fixed_deposits",
        "real_estate",
        "cash"
    ]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for table_name in tables:
            conditions = []
            params = []
            if account_type:
                conditions.append("account_type = ?")
                params.append(account_type)
            if user_id:
                conditions.append("user_id = ?")
                params.append(user_id)
            where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            df = db_read_sql(
                f"SELECT * FROM {table_name}{where}",
                conn,
                params=params if params else None
            )
            df.to_excel(writer, sheet_name=table_name, index=False)
    output.seek(0)
    return output.getvalue()


def insert_sample_data(conn, user_id=None):
    # Sample income - personal
    income_data = [
        ('Salary', 5000, 'USD', '2023-01-01', 'salary', 'personal', user_id),
        ('Freelance', 1000, 'USD', '2023-01-15', 'side', 'personal', user_id),
        ('Dividend', 200, 'USD', '2023-01-20', 'passive', 'personal', user_id),
        ('Salary', 5000, 'USD', '2023-02-01', 'salary', 'personal', user_id),
        ('Freelance', 1200, 'USD', '2023-02-15', 'side', 'personal', user_id),
        # Business
        ('Sales Revenue', 10000, 'USD', '2023-01-01', 'revenue', 'business', user_id),
        ('Service Income', 5000, 'USD', '2023-01-15', 'service', 'business', user_id),
        ('Sales Revenue', 12000, 'USD', '2023-02-01', 'revenue', 'business', user_id),
    ]
    conn.executemany("INSERT INTO income (source, amount, currency, date, type, account_type, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)", income_data)

    # Sample expenses - personal
    expenses_data = [
        ('Food', 800, 'USD', '2023-01-01', 'personal', user_id),
        ('Rent', 1500, 'USD', '2023-01-01', 'personal', user_id),
        ('Utilities', 200, 'USD', '2023-01-01', 'personal', user_id),
        ('Food', 850, 'USD', '2023-02-01', 'personal', user_id),
        ('Rent', 1500, 'USD', '2023-02-01', 'personal', user_id),
        # Business
        ('Office Rent', 2000, 'USD', '2023-01-01', 'business', user_id),
        ('Marketing', 1000, 'USD', '2023-01-15', 'business', user_id),
        ('Supplies', 500, 'USD', '2023-02-01', 'business', user_id),
    ]
    conn.executemany("INSERT INTO expenses (category, amount, currency, date, account_type, user_id) VALUES (?, ?, ?, ?, ?, ?)", expenses_data)

    # Sample investments - personal
    investments_data = [
        ('Stocks', 'AAPL', 10000, 12000, 'USD', '2022-01-01', 'personal', user_id),
        ('Mutual Funds', 'Vanguard', 5000, 5500, 'USD', '2022-06-01', 'personal', user_id),
        ('Crypto', 'BTC', 2000, 2500, 'USD', '2023-01-01', 'personal', user_id),
        # Business
        ('Equipment', 'Machinery', 20000, 18000, 'USD', '2022-01-01', 'business', user_id),
        ('Inventory', 'Stock', 5000, 6000, 'USD', '2023-01-01', 'business', user_id),
    ]
    conn.executemany("INSERT INTO investments (category, name, invested_amount, current_value, currency, date_purchased, account_type, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", investments_data)

    # Sample fixed deposits - personal
    fd_data = [
        ('Bank A', 10000, 5.0, '2025-01-01', 10500, 'USD', 'personal', user_id),
        ('Bank B', 15000, 4.5, '2024-06-01', 15750, 'USD', 'personal', user_id),
        # Business
        ('Corp Bank', 50000, 6.0, '2025-01-01', 53000, 'USD', 'business', user_id),
    ]
    conn.executemany("INSERT INTO fixed_deposits (bank, principal, interest_rate, maturity_date, maturity_value, currency, account_type, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", fd_data)

    # Sample real estate - personal
    re_data = [
        ('Apartment 1', 200000, 250000, 2000, 'USD', 'personal', user_id),
        ('House', 300000, 350000, 0, 'USD', 'personal', user_id),
        # Business
        ('Office Building', 500000, 600000, 10000, 'USD', 'business', user_id),
    ]
    conn.executemany("INSERT INTO real_estate (property_name, purchase_price, current_value, rental_income, currency, account_type, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)", re_data)

    # Sample cash - personal
    cash_data = [
        (5000, 'USD', '2023-01-01', 'personal', user_id),
        # Business
        (10000, 'USD', '2023-01-01', 'business', user_id),
    ]
    conn.executemany("INSERT INTO cash (amount, currency, date, account_type, user_id) VALUES (?, ?, ?, ?, ?)", cash_data)

    conn.commit()

def get_data(conn, table, date_filter=None, account_type=None, user_id=None):
    query = f"SELECT * FROM {table}"
    conditions = []
    params = []
    if date_filter:
        conditions.append("date >= ?")
        params.append(date_filter)
    if account_type:
        conditions.append("account_type = ?")
        params.append(account_type)
    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    df = db_read_sql(query, conn, params=params if params else None)
    return df

def calculate_net_worth(conn, account_type=None, user_id=None):
    EXCHANGE_RATES = {'USD': 1.0, 'EUR': 0.8537, 'INR': 95.11}  # last updated 2026-05-04

    def build_where(base_conditions, base_params):
        conds = list(base_conditions)
        params = list(base_params)
        if account_type:
            conds.append("account_type = ?")
            params.append(account_type)
        if user_id:
            conds.append("user_id = ?")
            params.append(user_id)
        return (" WHERE " + " AND ".join(conds)) if conds else "", params

    def convert_to_usd(amount, currency):
        return amount / EXCHANGE_RATES.get(currency, 1.0)

    def sum_usd_by_currency(table_name, value_col):
        where, params = build_where([], [])
        df = db_read_sql(
            f"SELECT currency, COALESCE(SUM({value_col}), 0) AS total_amount FROM {table_name}{where} GROUP BY currency",
            conn,
            params=params or None,
        )
        return sum(convert_to_usd(r['total_amount'], r['currency']) for _, r in df.iterrows())

    inv = sum_usd_by_currency("investments", "current_value")
    fd = sum_usd_by_currency("fixed_deposits", "maturity_value")
    re = sum_usd_by_currency("real_estate", "current_value")
    cash = sum_usd_by_currency("cash", "amount")

    return inv + fd + re + cash

def calculate_income_expenses(conn, period='monthly', account_type=None, user_id=None):
    EXCHANGE_RATES = {'USD': 1.0, 'EUR': 0.8537, 'INR': 95.11}  # last updated 2026-05-04

    def convert_to_usd(amount, currency):
        return amount / EXCHANGE_RATES.get(currency, 1.0)

    def sum_usd_by_currency(table_name):
        df = db_read_sql(
            f"SELECT currency, COALESCE(SUM(amount), 0) AS total_amount FROM {table_name}{where} GROUP BY currency",
            conn,
            params=params,
        )
        return sum(convert_to_usd(r['total_amount'], r['currency']) for _, r in df.iterrows())

    now = datetime.now()
    if period == 'monthly':
        start = now.replace(day=1).strftime('%Y-%m-%d')
    elif period == 'yearly':
        start = now.replace(month=1, day=1).strftime('%Y-%m-%d')
    else:
        start = '2000-01-01'

    conditions = ["date >= ?"]
    params = [start]
    if account_type:
        conditions.append("account_type = ?")
        params.append(account_type)
    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)
    where = " WHERE " + " AND ".join(conditions)

    income = sum_usd_by_currency("income")
    expenses = sum_usd_by_currency("expenses")

    savings_rate = ((income - expenses) / income * 100) if income > 0 else 0
    return income, expenses, savings_rate


def save_bank_statement_rows(conn, bank_name, source_name, currency, account_type, parsed_df, replace_existing=False, user_id=None):
    if parsed_df.empty:
        raise ValueError("No parsed bank statement rows to save.")

    if replace_existing:
        if user_id:
            conn.execute(
                "DELETE FROM bank_statements WHERE bank_name = ? AND account_type = ? AND user_id = ?",
                (bank_name, account_type, user_id)
            )
        else:
            conn.execute(
                "DELETE FROM bank_statements WHERE bank_name = ? AND account_type = ?",
                (bank_name, account_type)
            )

    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rows = []
    for _, row in parsed_df.iterrows():
        rows.append((
            bank_name,
            pd.to_datetime(row['date']).strftime('%Y-%m-%d'),
            str(row.get('description', '')),
            str(row.get('category', 'Other')),
            float(row.get('income_amount', 0) or 0),
            float(row.get('expense_amount', 0) or 0),
            float(row.get('net_amount', 0) or 0),
            currency,
            source_name,
            account_type,
            created_at,
            user_id
        ))

    conn.executemany(
        """
        INSERT INTO bank_statements (
            bank_name, txn_date, description, category, income_amount, expense_amount,
            net_amount, currency, source_name, account_type, created_at, user_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows
    )
    conn.commit()
    return len(rows)


def get_bank_statement_data(conn, account_type=None, user_id=None):
    query = "SELECT * FROM bank_statements"
    conditions = []
    params = []
    if account_type:
        conditions.append("account_type = ?")
        params.append(account_type)
    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY txn_date DESC, id DESC"
    return db_read_sql(query, conn, params=params if params else None)


def update_bank_statement_categories(conn, category_updates):
    if not category_updates:
        return 0

    normalized_updates = []
    for row_id, category in category_updates:
        normalized_updates.append((str(category or "Other").strip() or "Other", int(row_id)))

    conn.executemany(
        "UPDATE bank_statements SET category = ? WHERE id = ?",
        normalized_updates
    )
    conn.commit()
    return len(normalized_updates)


def delete_bank_statement_rows(conn, row_ids, user_id=None):
    if not row_ids:
        return 0

    normalized_ids = [int(row_id) for row_id in row_ids]
    placeholders = ",".join(["?" for _ in normalized_ids])
    cursor = conn.cursor()
    if user_id:
        cursor.execute(
            f"DELETE FROM bank_statements WHERE id IN ({placeholders}) AND user_id = ?",
            normalized_ids + [user_id]
        )
    else:
        cursor.execute(
            f"DELETE FROM bank_statements WHERE id IN ({placeholders})",
            normalized_ids
        )
    conn.commit()
    return cursor.rowcount

# Add more functions as needed