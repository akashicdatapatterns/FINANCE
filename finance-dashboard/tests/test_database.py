"""
Tests for database.py — auth, user management, CRUD, and financial calculations.
Uses an in-memory SQLite database via the `conn` / `conn_with_users` fixtures in conftest.py.
"""
import pytest
import pandas as pd

import database


# ---------------------------------------------------------------------------
# hash_password / verify_password
# ---------------------------------------------------------------------------

class TestHashPassword:
    def test_deterministic(self):
        assert database.hash_password("secret") == database.hash_password("secret")

    def test_different_passwords_differ(self):
        assert database.hash_password("abc") != database.hash_password("xyz")

    def test_verify_correct(self):
        h = database.hash_password("mypassword")
        assert database.verify_password("mypassword", h)

    def test_verify_wrong(self):
        h = database.hash_password("mypassword")
        assert not database.verify_password("wrong", h)


# ---------------------------------------------------------------------------
# register_user / authenticate_user
# ---------------------------------------------------------------------------

class TestRegisterUser:
    def test_successful_registration(self, conn):
        ok, err = database.register_user(
            conn, "alice", "pass123",
            first_name="Alice", last_name="Smith",
            email="alice@example.com",
            security_question="Pet name?", security_answer="Fluffy"
        )
        assert ok
        assert err == ""

    def test_duplicate_username_rejected(self, conn):
        database.register_user(
            conn, "bob", "pass123",
            first_name="Bob", last_name="Jones",
            email="bob@example.com",
            security_question="Pet?", security_answer="Rex"
        )
        ok, err = database.register_user(
            conn, "bob", "different",
            first_name="Bob", last_name="Jones",
            email="bob2@example.com",
            security_question="Pet?", security_answer="Rex"
        )
        assert not ok
        assert "already taken" in err

    def test_short_username_rejected(self, conn):
        ok, err = database.register_user(
            conn, "ab", "pass123",
            first_name="A", last_name="B",
            email="a@example.com",
            security_question="Q?", security_answer="A"
        )
        assert not ok

    def test_short_password_rejected(self, conn):
        ok, err = database.register_user(
            conn, "charlie", "abc",
            first_name="Charlie", last_name="Brown",
            email="c@example.com",
            security_question="Q?", security_answer="A"
        )
        assert not ok
        assert "6 characters" in err

    def test_missing_email_rejected(self, conn):
        ok, err = database.register_user(
            conn, "dave", "pass123",
            first_name="Dave", last_name="White",
            email="notanemail",
            security_question="Q?", security_answer="A"
        )
        assert not ok

    def test_missing_security_answer_rejected(self, conn):
        ok, err = database.register_user(
            conn, "eve", "pass123",
            first_name="Eve", last_name="Adams",
            email="eve@example.com",
            security_question="Pet?", security_answer=""
        )
        assert not ok


class TestAuthenticateUser:
    def test_correct_credentials(self, conn_with_users):
        user = database.authenticate_user(conn_with_users, "admin", "admin123")
        assert user is not None
        assert user["username"] == "admin"

    def test_wrong_password(self, conn_with_users):
        user = database.authenticate_user(conn_with_users, "admin", "wrongpass")
        assert user is None

    def test_nonexistent_user(self, conn_with_users):
        user = database.authenticate_user(conn_with_users, "nobody", "pass")
        assert user is None


# ---------------------------------------------------------------------------
# get_data — basic row filtering
# ---------------------------------------------------------------------------

class TestGetData:
    def _insert_income(self, conn, amount, currency="USD", account_type="personal", user_id=None):
        conn.execute(
            "INSERT INTO income (source, amount, currency, date, type, account_type, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Salary", amount, currency, "2026-05-01", "Fixed", account_type, user_id)
        )
        conn.commit()

    def test_returns_all_rows_without_filter(self, conn):
        self._insert_income(conn, 1000)
        self._insert_income(conn, 2000)
        df = database.get_data(conn, "income")
        assert len(df) == 2

    def test_filters_by_account_type(self, conn):
        self._insert_income(conn, 1000, account_type="personal")
        self._insert_income(conn, 9000, account_type="business")
        df = database.get_data(conn, "income", account_type="personal")
        assert len(df) == 1
        assert df.iloc[0]["amount"] == 1000

    def test_filters_by_user_id(self, conn):
        self._insert_income(conn, 500, user_id=101)
        self._insert_income(conn, 800, user_id=202)
        df = database.get_data(conn, "income", user_id=101)
        assert len(df) == 1
        assert df.iloc[0]["amount"] == 500

    def test_filters_by_date(self, conn):
        conn.execute(
            "INSERT INTO income (source, amount, currency, date, type, account_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("Old", 100, "USD", "2020-01-01", "Fixed", "personal")
        )
        self._insert_income(conn, 500)  # date = 2026-05-01
        conn.commit()
        df = database.get_data(conn, "income", date_filter="2025-01-01")
        assert len(df) == 1
        assert df.iloc[0]["amount"] == 500


# ---------------------------------------------------------------------------
# calculate_net_worth
# ---------------------------------------------------------------------------

class TestCalculateNetWorth:
    def test_zero_when_empty(self, conn):
        result = database.calculate_net_worth(conn)
        assert result == 0.0

    def test_sum_includes_investments_fd_realestate_cash(self, conn):
        conn.execute(
            "INSERT INTO investments (category, name, invested_amount, current_value, currency, date_purchased, account_type) "
            "VALUES ('Stocks', 'AAPL', 1000, 1500, 'USD', '2025-01-01', 'personal')"
        )
        conn.execute(
            "INSERT INTO cash (amount, currency, date, account_type) VALUES (500, 'USD', '2026-01-01', 'personal')"
        )
        conn.commit()
        result = database.calculate_net_worth(conn)
        assert result == pytest.approx(2000.0)

    def test_filters_by_account_type(self, conn):
        conn.execute(
            "INSERT INTO cash (amount, currency, date, account_type) VALUES (1000, 'USD', '2026-01-01', 'personal')"
        )
        conn.execute(
            "INSERT INTO cash (amount, currency, date, account_type) VALUES (9000, 'USD', '2026-01-01', 'business')"
        )
        conn.commit()
        result = database.calculate_net_worth(conn, account_type="personal")
        assert result == pytest.approx(1000.0)
