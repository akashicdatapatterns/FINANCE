"""
Tests for pure utility functions defined in app.py.

app.py calls st.set_page_config() at module level, so we mock the entire
streamlit module before importing to keep tests free of Streamlit state.
"""
import sys
import types
import pytest
import pandas as pd
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub out streamlit before app.py is imported
# ---------------------------------------------------------------------------

class _SessionState:
    """Minimal object that mimics Streamlit's SessionState for testing."""
    _data: dict

    def __init__(self):
        object.__setattr__(self, "_data", {})

    def __getattr__(self, name):
        return object.__getattribute__(self, "_data").get(name)

    def __setattr__(self, name, value):
        object.__getattribute__(self, "_data")[name] = value

    def __contains__(self, key):
        return key in object.__getattribute__(self, "_data")

    def get(self, key, default=None):
        return object.__getattribute__(self, "_data").get(key, default)


def _make_streamlit_stub():
    st = MagicMock()
    st.__name__ = "streamlit"
    st.session_state = _SessionState()

    # Layout: tabs/columns must return iterables of the correct length
    def _tabs(labels):
        return [MagicMock(__enter__=MagicMock(return_value=MagicMock()), __exit__=MagicMock(return_value=False)) for _ in labels]

    def _columns(spec):
        n = spec if isinstance(spec, int) else len(spec)
        return [MagicMock(__enter__=MagicMock(return_value=MagicMock()), __exit__=MagicMock(return_value=False)) for _ in range(n)]

    st.tabs = _tabs
    st.columns = _columns

    def _selectbox(label, options=None, *args, **kwargs):
        if options:
            return options[0]
        return ""

    def _radio(label, options=None, *args, **kwargs):
        if options:
            return options[0]
        return ""

    for attr in ("text_input", "text_area"):
        setattr(st, attr, MagicMock(return_value=""))
    st.selectbox = _selectbox
    st.radio = _radio
    st.number_input = MagicMock(return_value=0)
    st.checkbox = MagicMock(return_value=False)
    st.button = MagicMock(return_value=False)
    st.date_input = MagicMock(return_value=None)

    # Sidebar: mirror the same safe stubs
    sidebar = MagicMock()
    sidebar.text_input = MagicMock(return_value="")
    sidebar.selectbox = _selectbox
    sidebar.radio = _radio
    sidebar.button = MagicMock(return_value=False)
    sidebar.checkbox = MagicMock(return_value=False)
    st.sidebar = sidebar

    return st


# Only inject the stub once per process
if "streamlit" not in sys.modules:
    sys.modules["streamlit"] = _make_streamlit_stub()
else:
    # Patch set_page_config so re-import doesn't raise
    sys.modules["streamlit"].set_page_config = MagicMock()

# Also stub pdfplumber to avoid heavy dependency in unit tests
if "pdfplumber" not in sys.modules:
    sys.modules["pdfplumber"] = types.ModuleType("pdfplumber")

import app  # noqa: E402  (must come after stubs)


# ---------------------------------------------------------------------------
# convert_currency
# ---------------------------------------------------------------------------

class TestConvertCurrency:
    def test_same_currency_returns_same(self):
        assert app.convert_currency(100, "USD", "USD") == 100

    def test_usd_to_eur(self):
        result = app.convert_currency(100, "USD", "EUR")
        assert result == pytest.approx(100 * app.EXCHANGE_RATES["EUR"])

    def test_eur_to_inr(self):
        result = app.convert_currency(1, "EUR", "INR")
        expected = (1 / app.EXCHANGE_RATES["EUR"]) * app.EXCHANGE_RATES["INR"]
        assert result == pytest.approx(expected)

    def test_zero_amount(self):
        assert app.convert_currency(0, "USD", "INR") == 0.0


# ---------------------------------------------------------------------------
# format_currency
# ---------------------------------------------------------------------------

class TestFormatCurrency:
    def test_usd_symbol(self):
        assert app.format_currency(1000, "USD").startswith("$")

    def test_eur_symbol(self):
        assert app.format_currency(500, "EUR").startswith("€")

    def test_inr_symbol(self):
        assert app.format_currency(250, "INR").startswith("₹")

    def test_two_decimal_places(self):
        result = app.format_currency(1234.5, "USD")
        assert "1,234.50" in result

    def test_unknown_currency_uses_code(self):
        result = app.format_currency(100, "GBP")
        assert "GBP" in result


# ---------------------------------------------------------------------------
# categorize_transaction
# ---------------------------------------------------------------------------

class TestCategorizeTransaction:
    @pytest.mark.parametrize("desc,expected", [
        ("SALARY CREDIT", "Salary"),
        ("PAYROLL 2026-05", "Salary"),
        ("NEFT TRANSFER TO 12345", "Transfer"),
        ("UPI/PAYMENT/ZOMATO", "Transfer"),  # 'upi' matched before 'zomato' in category_map
        ("UBER RIDE", "Transport"),
        ("AMAZON PURCHASE", "Shopping"),
        ("ATM CASH WITHDRAWAL", "Cash Withdrawal"),
        ("HOSPITAL CHARGES", "Healthcare"),
        ("ELECTRICITY BILL PAYMENT", "Utilities"),
        ("SOME RANDOM UNKNOWN TXN", "Other"),
    ])
    def test_known_categories(self, desc, expected):
        assert app.categorize_transaction(desc) == expected

    def test_case_insensitive(self):
        assert app.categorize_transaction("SALARY") == app.categorize_transaction("salary")


# ---------------------------------------------------------------------------
# to_numeric_series
# ---------------------------------------------------------------------------

class TestToNumericSeries:
    def test_plain_numbers(self):
        s = pd.Series(["100", "200.50", "0"])
        result = app.to_numeric_series(s)
        assert list(result) == pytest.approx([100.0, 200.50, 0.0])

    def test_currency_symbols_stripped(self):
        s = pd.Series(["$1,000", "€500", "₹250"])
        result = app.to_numeric_series(s)
        assert result[0] == pytest.approx(1000.0)
        assert result[1] == pytest.approx(500.0)
        assert result[2] == pytest.approx(250.0)

    def test_dr_marker_makes_negative(self):
        s = pd.Series(["500 DR", "300 dr"])
        result = app.to_numeric_series(s)
        assert all(v < 0 for v in result)

    def test_cr_marker_makes_positive(self):
        s = pd.Series(["500 CR", "-300 CR"])
        result = app.to_numeric_series(s)
        assert all(v > 0 for v in result)

    def test_parentheses_negative(self):
        s = pd.Series(["(200)"])
        result = app.to_numeric_series(s)
        assert result[0] == pytest.approx(-200.0)

    def test_nan_becomes_zero(self):
        s = pd.Series([None, float("nan"), ""])
        result = app.to_numeric_series(s)
        assert list(result) == pytest.approx([0.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# parse_mixed_date_series
# ---------------------------------------------------------------------------

class TestParseMixedDateSeries:
    def test_iso_format(self):
        # dayfirst=True treats "2026-05-01" as year=2026, day=5, month=1
        s = pd.Series(["2026-05-01"])
        result = app.parse_mixed_date_series(s)
        assert result[0].year == 2026
        assert result[0].day == 5
        assert result[0].month == 1

    def test_day_first_format(self):
        s = pd.Series(["01/05/2026"])
        result = app.parse_mixed_date_series(s)
        assert result[0].day == 1
        assert result[0].month == 5

    def test_invalid_becomes_nat(self):
        s = pd.Series(["not-a-date"])
        result = app.parse_mixed_date_series(s)
        assert pd.isna(result[0])
