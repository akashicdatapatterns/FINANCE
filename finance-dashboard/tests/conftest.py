"""
Shared pytest fixtures for the Finance Dashboard test suite.
"""
import sys
import os
import pytest

# Ensure finance-dashboard/ is on the path so database.py can be imported directly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database


@pytest.fixture
def conn():
    """In-memory SQLite connection with all tables created and default users seeded."""
    connection = database.create_connection(":memory:")
    database.create_tables(connection)
    database.create_users_table(connection)
    yield connection
    connection.close()


@pytest.fixture
def conn_with_users(conn):
    """In-memory connection that also has the three default users inserted."""
    database.insert_default_users(conn)
    return conn
