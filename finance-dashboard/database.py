import os
import sqlite3
import hashlib
import pandas as pd
from datetime import datetime

def create_connection(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        conn.execute("PRAGMA busy_timeout = 30000")  # Wait up to 30 seconds for lock to release
    except sqlite3.Error as e:
        print(e)
    return conn

def create_tables(conn):
    sql_create_income_table = """
    CREATE TABLE IF NOT EXISTS income (
        id INTEGER PRIMARY KEY,
        source TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        date TEXT NOT NULL,
        type TEXT NOT NULL,
        account_type TEXT DEFAULT 'personal'
    );
    """
    sql_create_expenses_table = """
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        date TEXT NOT NULL,
        account_type TEXT DEFAULT 'personal'
    );
    """
    sql_create_investments_table = """
    CREATE TABLE IF NOT EXISTS investments (
        id INTEGER PRIMARY KEY,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        invested_amount REAL NOT NULL,
        current_value REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        date_purchased TEXT NOT NULL,
        account_type TEXT DEFAULT 'personal'
    );
    """
    sql_create_fixed_deposits_table = """
    CREATE TABLE IF NOT EXISTS fixed_deposits (
        id INTEGER PRIMARY KEY,
        bank TEXT NOT NULL,
        principal REAL NOT NULL,
        interest_rate REAL NOT NULL,
        maturity_date TEXT NOT NULL,
        maturity_value REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        account_type TEXT DEFAULT 'personal'
    );
    """
    sql_create_real_estate_table = """
    CREATE TABLE IF NOT EXISTS real_estate (
        id INTEGER PRIMARY KEY,
        property_name TEXT NOT NULL,
        purchase_price REAL NOT NULL,
        current_value REAL NOT NULL,
        rental_income REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        account_type TEXT DEFAULT 'personal'
    );
    """
    sql_create_cash_table = """
    CREATE TABLE IF NOT EXISTS cash (
        id INTEGER PRIMARY KEY,
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        date TEXT NOT NULL,
        account_type TEXT DEFAULT 'personal'
    );
    """
    try:
        c = conn.cursor()
        c.execute(sql_create_income_table)
        c.execute(sql_create_expenses_table)
        c.execute(sql_create_investments_table)
        c.execute(sql_create_fixed_deposits_table)
        c.execute(sql_create_real_estate_table)
        c.execute(sql_create_cash_table)
        conn.commit()
    except sqlite3.Error as e:
        print(e)


def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def verify_password(password, password_hash):
    return hash_password(password) == password_hash


def create_users_table(conn):
    sql_create_users_table = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'user'
    );
    """
    try:
        c = conn.cursor()
        c.execute(sql_create_users_table)
        conn.commit()
    except sqlite3.Error as e:
        print(e)


def get_user(conn, username):
    query = "SELECT * FROM users WHERE username = ?"
    df = pd.read_sql_query(query, conn, params=(username,))
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def get_env_password(username, default_password):
    env_key = f"{username.upper()}_PASSWORD"
    return os.getenv(env_key, default_password)


def insert_default_users(conn):
    try:
        user_count = pd.read_sql_query("SELECT COUNT(*) FROM users", conn).iloc[0, 0]
    except Exception:
        user_count = 0
    if user_count == 0:
        default_users = [
            ('admin', hash_password(get_env_password('admin', 'admin123')), 'admin'),
            ('personal', hash_password(get_env_password('personal', 'personal123')), 'personal'),
            ('business', hash_password(get_env_password('business', 'business123')), 'business')
        ]
        conn.executemany("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", default_users)
        conn.commit()


def authenticate_user(conn, username, password):
    user = get_user(conn, username)
    if user and verify_password(password, user['password_hash']):
        return user
    return None


def insert_sample_data(conn):
    # Sample income - personal
    income_data = [
        ('Salary', 5000, 'USD', '2023-01-01', 'salary', 'personal'),
        ('Freelance', 1000, 'USD', '2023-01-15', 'side', 'personal'),
        ('Dividend', 200, 'USD', '2023-01-20', 'passive', 'personal'),
        ('Salary', 5000, 'USD', '2023-02-01', 'salary', 'personal'),
        ('Freelance', 1200, 'USD', '2023-02-15', 'side', 'personal'),
        # Business
        ('Sales Revenue', 10000, 'USD', '2023-01-01', 'revenue', 'business'),
        ('Service Income', 5000, 'USD', '2023-01-15', 'service', 'business'),
        ('Sales Revenue', 12000, 'USD', '2023-02-01', 'revenue', 'business'),
    ]
    conn.executemany("INSERT INTO income (source, amount, currency, date, type, account_type) VALUES (?, ?, ?, ?, ?, ?)", income_data)

    # Sample expenses - personal
    expenses_data = [
        ('Food', 800, 'USD', '2023-01-01', 'personal'),
        ('Rent', 1500, 'USD', '2023-01-01', 'personal'),
        ('Utilities', 200, 'USD', '2023-01-01', 'personal'),
        ('Food', 850, 'USD', '2023-02-01', 'personal'),
        ('Rent', 1500, 'USD', '2023-02-01', 'personal'),
        # Business
        ('Office Rent', 2000, 'USD', '2023-01-01', 'business'),
        ('Marketing', 1000, 'USD', '2023-01-15', 'business'),
        ('Supplies', 500, 'USD', '2023-02-01', 'business'),
    ]
    conn.executemany("INSERT INTO expenses (category, amount, currency, date, account_type) VALUES (?, ?, ?, ?, ?)", expenses_data)

    # Sample investments - personal
    investments_data = [
        ('Stocks', 'AAPL', 10000, 12000, 'USD', '2022-01-01', 'personal'),
        ('Mutual Funds', 'Vanguard', 5000, 5500, 'USD', '2022-06-01', 'personal'),
        ('Crypto', 'BTC', 2000, 2500, 'USD', '2023-01-01', 'personal'),
        # Business
        ('Equipment', 'Machinery', 20000, 18000, 'USD', '2022-01-01', 'business'),
        ('Inventory', 'Stock', 5000, 6000, 'USD', '2023-01-01', 'business'),
    ]
    conn.executemany("INSERT INTO investments (category, name, invested_amount, current_value, currency, date_purchased, account_type) VALUES (?, ?, ?, ?, ?, ?, ?)", investments_data)

    # Sample fixed deposits - personal
    fd_data = [
        ('Bank A', 10000, 5.0, '2025-01-01', 10500, 'USD', 'personal'),
        ('Bank B', 15000, 4.5, '2024-06-01', 15750, 'USD', 'personal'),
        # Business
        ('Corp Bank', 50000, 6.0, '2025-01-01', 53000, 'USD', 'business'),
    ]
    conn.executemany("INSERT INTO fixed_deposits (bank, principal, interest_rate, maturity_date, maturity_value, currency, account_type) VALUES (?, ?, ?, ?, ?, ?, ?)", fd_data)

    # Sample real estate - personal
    re_data = [
        ('Apartment 1', 200000, 250000, 2000, 'USD', 'personal'),
        ('House', 300000, 350000, 0, 'USD', 'personal'),
        # Business
        ('Office Building', 500000, 600000, 10000, 'USD', 'business'),
    ]
    conn.executemany("INSERT INTO real_estate (property_name, purchase_price, current_value, rental_income, currency, account_type) VALUES (?, ?, ?, ?, ?, ?)", re_data)

    # Sample cash - personal
    cash_data = [
        (5000, 'USD', '2023-01-01', 'personal'),
        # Business
        (10000, 'USD', '2023-01-01', 'business'),
    ]
    conn.executemany("INSERT INTO cash (amount, currency, date, account_type) VALUES (?, ?, ?, ?)", cash_data)

    conn.commit()

def get_data(conn, table, date_filter=None, account_type=None):
    query = f"SELECT * FROM {table}"
    conditions = []
    if date_filter:
        conditions.append(f"date >= '{date_filter}'")
    if account_type:
        conditions.append(f"account_type = '{account_type}'")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    df = pd.read_sql_query(query, conn)
    return df

def calculate_net_worth(conn, account_type=None):
    # Exchange rates (base USD)
    EXCHANGE_RATES = {
        'USD': 1.0,
        'EUR': 0.85,
        'INR': 83.0
    }
    
    def convert_to_usd(amount, currency):
        return amount / EXCHANGE_RATES.get(currency, 1.0)
    
    # Investments
    inv_query = "SELECT current_value, currency FROM investments"
    if account_type:
        inv_query += f" WHERE account_type = '{account_type}'"
    inv_df = pd.read_sql_query(inv_query, conn)
    inv = sum(convert_to_usd(row['current_value'], row['currency']) for _, row in inv_df.iterrows())
    
    # FD
    fd_query = "SELECT maturity_value, currency FROM fixed_deposits"
    if account_type:
        fd_query += f" WHERE account_type = '{account_type}'"
    fd_df = pd.read_sql_query(fd_query, conn)
    fd = sum(convert_to_usd(row['maturity_value'], row['currency']) for _, row in fd_df.iterrows())
    
    # Real Estate
    re_query = "SELECT current_value, currency FROM real_estate"
    if account_type:
        re_query += f" WHERE account_type = '{account_type}'"
    re_df = pd.read_sql_query(re_query, conn)
    re = sum(convert_to_usd(row['current_value'], row['currency']) for _, row in re_df.iterrows())
    
    # Cash
    cash_query = "SELECT amount, currency FROM cash"
    if account_type:
        cash_query += f" WHERE account_type = '{account_type}'"
    cash_df = pd.read_sql_query(cash_query, conn)
    cash = sum(convert_to_usd(row['amount'], row['currency']) for _, row in cash_df.iterrows())
    
    return inv + fd + re + cash

def calculate_income_expenses(conn, period='monthly', account_type=None):
    # Exchange rates (base USD)
    EXCHANGE_RATES = {
        'USD': 1.0,
        'EUR': 0.85,
        'INR': 90.0
    }
    
    def convert_to_usd(amount, currency):
        return amount / EXCHANGE_RATES.get(currency, 1.0)
    
    now = datetime.now()
    if period == 'monthly':
        start = now.replace(day=1).strftime('%Y-%m-%d')
    elif period == 'yearly':
        start = now.replace(month=1, day=1).strftime('%Y-%m-%d')
    else:
        start = '2023-01-01'

    income_query = f"SELECT amount, currency FROM income WHERE date >= '{start}'"
    expenses_query = f"SELECT amount, currency FROM expenses WHERE date >= '{start}'"
    if account_type:
        income_query += f" AND account_type = '{account_type}'"
        expenses_query += f" AND account_type = '{account_type}'"
    
    income_df = pd.read_sql_query(income_query, conn)
    expenses_df = pd.read_sql_query(expenses_query, conn)
    
    income = sum(convert_to_usd(row['amount'], row['currency']) for _, row in income_df.iterrows())
    expenses = sum(convert_to_usd(row['amount'], row['currency']) for _, row in expenses_df.iterrows())
    
    savings_rate = ((income - expenses) / income * 100) if income > 0 else 0
    return income, expenses, savings_rate

# Add more functions as needed