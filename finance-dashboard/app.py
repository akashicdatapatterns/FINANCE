import io
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pdfplumber
from database import create_connection, create_tables, create_users_table, insert_sample_data, insert_default_users, authenticate_user, register_user, get_user, get_user_by_email, verify_security_answer, reset_user_password, update_user_profile, import_excel_to_db, export_db_to_excel, get_data, calculate_net_worth, calculate_income_expenses, save_bank_statement_rows, get_bank_statement_data, update_bank_statement_categories, delete_bank_statement_rows, migrate_add_user_id, get_all_usernames, get_last_connection_error
from datetime import datetime, date as dt_date

# Page config
st.set_page_config(page_title="Personal Finance Dashboard", layout="wide", initial_sidebar_state="expanded")

# Exchange rates (base USD) — last updated 2026-05-04 from xe.com
EXCHANGE_RATES = {
    'USD': 1.0,
    'EUR': 0.8537,
    'INR': 95.11
}

BANK_COLUMN_ALIASES = {
    "date": ["date", "txn_date", "transaction_date", "value_date", "posting_date"],
    "description": ["description", "narration", "remarks", "details", "particulars", "transaction_details", "reference"],
    "amount": ["amount", "transaction_amount", "txn_amount"],
    "debit": ["debit", "withdrawal", "withdrawal_amt", "debit_amount", "dr"],
    "credit": ["credit", "deposit", "credit_amount", "cr"],
    "direction": ["dr_cr", "dr/cr", "cr_dr", "txn_type", "transaction_type", "type", "indicator"],
    "balance": ["balance", "available_balance", "running_balance", "closing_balance"]
}

def convert_currency(amount, from_currency, to_currency):
    if from_currency == to_currency:
        return amount
    # Convert to USD first, then to target
    usd_amount = amount / EXCHANGE_RATES[from_currency]
    return usd_amount * EXCHANGE_RATES[to_currency]

def format_currency(amount, currency):
    symbols = {'USD': '$', 'EUR': '€', 'INR': '₹'}
    symbol = symbols.get(currency, currency)
    return f"{symbol}{amount:,.2f}"


def apply_designer_ui():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;700;800&display=swap');

        :root {
            --bg-main: linear-gradient(135deg, #0a1020 0%, #121f3c 45%, #1e3a5f 100%);
            --text-main: #eaf2ff;
            --text-soft: #b7c5de;
            --panel: rgba(255, 255, 255, 0.06);
            --panel-border: rgba(255, 255, 255, 0.16);
            --accent: #ff5a5f;
            --accent-soft: rgba(255, 90, 95, 0.2);
        }

        .stApp {
            font-family: 'Manrope', 'Segoe UI', sans-serif;
            background: var(--bg-main);
            color: var(--text-main);
        }

        [data-testid="stAppViewContainer"] {
            background: transparent;
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }

        h1, h2, h3 {
            color: var(--text-main);
            letter-spacing: -0.02em;
        }

        p, label, .stMarkdown {
            color: var(--text-soft);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(7, 12, 24, 0.95) 0%, rgba(12, 22, 42, 0.92) 100%);
            border-right: 1px solid var(--panel-border);
        }

        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span {
            color: #dbe7ff;
        }

        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] [role="radiogroup"] > label {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 12px;
        }

        [data-testid="stSidebar"] [role="radiogroup"] > label {
            margin-bottom: 0.45rem;
            padding: 0.35rem 0.55rem;
            transition: all 0.2s ease;
        }

        [data-testid="stSidebar"] [role="radiogroup"] > label:hover {
            border-color: rgba(255, 255, 255, 0.28);
            background: rgba(255, 255, 255, 0.09);
        }

        /* Sidebar nav expander header */
        [data-testid="stSidebar"] details > summary {
            font-size: 1.05rem;
            font-weight: 800;
            letter-spacing: 0.04em;
            color: #ffffff;
            padding: 0.55rem 0.2rem;
            cursor: pointer;
            user-select: none;
        }

        [data-testid="stSidebar"] details[open] > summary {
            color: var(--accent);
        }

        /* Hover-expand: show nav content even when collapsed */
        [data-testid="stSidebar"] details.nav-expander:not([open]):hover > div {
            display: block !important;
        }

        /* Nav buttons inside expander */
        [data-testid="stSidebar"] details.nav-expander .stButton > button {
            background: transparent;
            border: none;
            border-left: 3px solid transparent;
            border-radius: 0 8px 8px 0;
            color: #b7c5de;
            font-weight: 600;
            font-size: 0.92rem;
            text-align: left;
            justify-content: flex-start;
            width: 100%;
            padding: 0.5rem 0.75rem;
            margin: 0.1rem 0;
            transition: all 0.18s ease;
        }

        [data-testid="stSidebar"] details.nav-expander .stButton > button:hover {
            background: rgba(255, 255, 255, 0.07);
            border-left-color: rgba(255, 255, 255, 0.45);
            color: #ffffff;
        }

        [data-testid="stMetric"] {
            background: var(--panel);
            border: 1px solid var(--panel-border);
            border-radius: 14px;
            padding: 0.5rem 0.75rem;
            backdrop-filter: blur(4px);
        }

        .stButton > button {
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.26);
            background: rgba(255, 255, 255, 0.08);
            color: #f6f9ff;
            font-weight: 700;
            transition: all 0.2s ease;
        }

        .stButton > button:hover {
            border-color: var(--accent);
            background: rgba(255, 90, 95, 0.16);
            color: #ffffff;
        }

        [data-testid="stDataFrame"] {
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            overflow: hidden;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def normalize_column_name(name):
    return str(name).strip().lower().replace(" ", "_")


def find_first_matching_column(columns, aliases):
    for alias in aliases:
        if alias in columns:
            return alias
    return None


def to_numeric_series(series):
    raw_series = series.fillna("").astype(str).str.strip()
    lowered = raw_series.str.lower()

    # Detect explicit text-based direction markers.
    has_dr_marker = lowered.str.contains(r"\bdr\b|\bdebit\b|\bwithdrawal\b", regex=True)
    has_cr_marker = lowered.str.contains(r"\bcr\b|\bcredit\b|\bdeposit\b", regex=True)
    has_paren_negative = lowered.str.contains(r"^\(.*\)$", regex=True)
    has_trailing_minus = lowered.str.contains(r"-\s*$", regex=True)

    # Strip all non-numeric characters except leading minus and decimal point.
    clean_series = (
        raw_series
        .str.replace(r"(?i)\b(cr|dr|credit|debit|withdrawal|deposit)\b", "", regex=True)
        .str.replace(r"[$,₹€\s]", "", regex=True)
        .str.replace("(", "", regex=False)
        .str.replace(")", "", regex=False)
        .str.replace(r"-\s*$", "", regex=True)
        .str.replace(r"[^0-9.\-]", "", regex=True)
        .str.strip()
    )

    # Parse: this preserves any leading '-' already in the cleaned string.
    numeric = pd.to_numeric(clean_series, errors="coerce").fillna(0.0)

    # Apply text-based direction overrides on top of the parsed value.
    # CR/deposit markers -> always positive.
    # DR/debit/withdrawal or parentheses/trailing-minus -> always negative.
    force_negative = has_dr_marker | has_paren_negative | has_trailing_minus
    force_positive = has_cr_marker & ~force_negative

    numeric = numeric.copy()
    numeric[force_negative] = -numeric[force_negative].abs()
    numeric[force_positive] = numeric[force_positive].abs()

    return numeric


def parse_mixed_date_series(series):
    # Try day-first parsing first, then retry unresolved values with month-first.
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=True)
    unresolved = parsed.isna()
    if unresolved.any():
        parsed.loc[unresolved] = pd.to_datetime(series[unresolved], errors="coerce", dayfirst=False)
    return parsed


def categorize_transaction(description):
    desc = str(description).lower()
    category_map = {
        "Salary": ["salary", "payroll", "wage"],
        "Business Income": ["invoice", "client", "payment received", "sales"],
        "Investment Income": ["dividend", "interest", "capital gain"],
        "Transfer": ["neft", "rtgs", "imps", "upi", "transfer"],
        "Rent": ["rent", "lease"],
        "Utilities": ["electric", "water", "gas", "internet", "mobile", "broadband"],
        "Groceries": ["grocery", "supermarket", "mart"],
        "Dining": ["restaurant", "cafe", "food", "swiggy", "zomato"],
        "Transport": ["fuel", "petrol", "diesel", "uber", "ola", "metro", "bus"],
        "Healthcare": ["hospital", "pharmacy", "medical", "doctor"],
        "Shopping": ["amazon", "flipkart", "shopping", "store"],
        "EMI/Loan": ["emi", "loan", "credit card", "repayment"],
        "Cash Withdrawal": ["atm", "cash withdrawal"]
    }
    for category, keywords in category_map.items():
        if any(keyword in desc for keyword in keywords):
            return category
    return "Other"


def validate_upload(uploaded_file, max_mb=10):
    """Validate uploaded file size and magic-byte MIME type.

    Raises ValueError with a user-facing message on any violation.
    Returns True when the file is safe to process.
    """
    # --- size check ---
    uploaded_file.seek(0, 2)          # seek to end
    size_bytes = uploaded_file.tell()
    uploaded_file.seek(0)             # reset to start
    if size_bytes > max_mb * 1024 * 1024:
        raise ValueError(
            f"File is too large ({size_bytes / 1024 / 1024:.1f} MB). "
            f"Maximum allowed size is {max_mb} MB."
        )

    # --- magic-byte MIME check ---
    header = uploaded_file.read(8)
    uploaded_file.seek(0)

    name = uploaded_file.name.lower()
    if name.endswith(".pdf"):
        if not header.startswith(b"%PDF"):
            raise ValueError("File does not appear to be a valid PDF.")
    elif name.endswith(".xlsx"):
        if not header.startswith(b"PK\x03\x04"):
            raise ValueError("File does not appear to be a valid Excel (.xlsx) workbook.")
    elif name.endswith(".xls"):
        if not header.startswith(b"\xd0\xcf\x11\xe0"):
            raise ValueError("File does not appear to be a valid Excel (.xls) workbook.")
    elif name.endswith(".csv"):
        try:
            header.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("CSV file contains non-text content and may be corrupted.")

    return True


def extract_pdf_tables(uploaded_file):
    tables = {}
    with pdfplumber.open(uploaded_file) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            page_tables = page.extract_tables() or []
            for table_index, table in enumerate(page_tables, start=1):
                if not table or len(table) < 2:
                    continue
                header = [normalize_column_name(cell) if cell else f"column_{col_index + 1}" for col_index, cell in enumerate(table[0])]
                data_rows = table[1:]
                frame = pd.DataFrame(data_rows, columns=header)
                frame = frame.dropna(how="all")
                if frame.empty:
                    continue
                key = f"Page {index} - Table {table_index}"
                tables[key] = frame
    if not tables:
        raise ValueError("No table could be extracted from the PDF. Use a PDF statement with tabular transaction data.")
    return tables


def load_bank_statement_sources(uploaded_file):
    file_name = uploaded_file.name.lower()
    if file_name.endswith(".csv"):
        raw_df = pd.read_csv(uploaded_file)
        return {"CSV Data": raw_df}
    elif file_name.endswith((".xlsx", ".xls")):
        workbook = pd.read_excel(uploaded_file, sheet_name=None)
        return workbook
    elif file_name.endswith(".pdf"):
        return extract_pdf_tables(uploaded_file)
    else:
        raise ValueError("Unsupported file format. Please upload CSV, Excel, or PDF.")


def suggest_bank_statement_mapping(columns):
    normalized_columns = [normalize_column_name(col) for col in columns]
    available_cols = set(normalized_columns)

    return {
        "date": find_first_matching_column(available_cols, BANK_COLUMN_ALIASES["date"]),
        "description": find_first_matching_column(available_cols, BANK_COLUMN_ALIASES["description"]),
        "amount": find_first_matching_column(available_cols, BANK_COLUMN_ALIASES["amount"]),
        "debit": find_first_matching_column(available_cols, BANK_COLUMN_ALIASES["debit"]),
        "credit": find_first_matching_column(available_cols, BANK_COLUMN_ALIASES["credit"]),
        "direction": find_first_matching_column(available_cols, BANK_COLUMN_ALIASES["direction"]),
        "balance": find_first_matching_column(available_cols, BANK_COLUMN_ALIASES["balance"]),
    }


def normalize_bank_statement(raw_df, column_mapping):
    raw_df = raw_df.copy()

    if raw_df.empty:
        raise ValueError("Uploaded bank statement is empty.")

    raw_df.columns = [normalize_column_name(col) for col in raw_df.columns]

    date_col = column_mapping.get("date")
    description_col = column_mapping.get("description")
    amount_col = column_mapping.get("amount")
    debit_col = column_mapping.get("debit")
    credit_col = column_mapping.get("credit")
    direction_col = column_mapping.get("direction")
    balance_col = column_mapping.get("balance")

    if not date_col:
        raise ValueError("Select the date column before running analysis.")
    if not description_col:
        raise ValueError("Select the description column before running analysis.")
    if not amount_col and not (debit_col and credit_col) and not balance_col:
        raise ValueError("Select either a signed Amount column, both Debit and Credit columns, or at least a Balance column for fallback inference.")

    missing_cols = [col for col in [date_col, description_col, amount_col, debit_col, credit_col, direction_col, balance_col] if col and col not in raw_df.columns]
    if missing_cols:
        raise ValueError(f"Selected columns were not found in the uploaded data: {', '.join(missing_cols)}")

    parsed_df = pd.DataFrame()
    parsed_df["date"] = parse_mixed_date_series(raw_df[date_col])
    parsed_df["description"] = raw_df[description_col].astype(str).fillna("Unknown Transaction")

    if amount_col:
        amount_series = to_numeric_series(raw_df[amount_col])
        if direction_col:
            direction_series = raw_df[direction_col].fillna("").astype(str).str.lower()
            is_debit = direction_series.str.contains(r"\bdr\b|\bdebit\b|\bwithdrawal\b", regex=True)
            is_credit = direction_series.str.contains(r"\bcr\b|\bcredit\b|\bdeposit\b", regex=True)
            parsed_df["expense_amount"] = amount_series.abs().where(is_debit, 0.0)
            parsed_df["income_amount"] = amount_series.abs().where(is_credit, 0.0)
            uncategorized = ~(is_debit | is_credit)
            if uncategorized.any():
                fallback_signed = amount_series.where(uncategorized, 0.0)
                parsed_df.loc[uncategorized, "income_amount"] = fallback_signed.clip(lower=0)
                parsed_df.loc[uncategorized, "expense_amount"] = (-fallback_signed).clip(lower=0)
        else:
            parsed_df["income_amount"] = amount_series.clip(lower=0)
            parsed_df["expense_amount"] = (-amount_series).clip(lower=0)
    else:
        debit_series = to_numeric_series(raw_df[debit_col])
        credit_series = to_numeric_series(raw_df[credit_col])
        parsed_df["income_amount"] = credit_series.abs()
        parsed_df["expense_amount"] = debit_series.abs()

    parsed_df["net_amount"] = parsed_df["income_amount"] - parsed_df["expense_amount"]
    parsed_df["transaction_type"] = parsed_df["net_amount"].apply(lambda x: "Income" if x >= 0 else "Expense")
    parsed_df["category"] = parsed_df["description"].apply(categorize_transaction)

    if balance_col:
        parsed_df["balance"] = to_numeric_series(raw_df[balance_col])

    parsed_df = parsed_df.dropna(subset=["date"]).sort_values("date")
    non_zero_tx = (parsed_df["income_amount"] > 0) | (parsed_df["expense_amount"] > 0)

    # Fallback: infer transaction amounts from balance delta when amount fields are empty.
    if balance_col and int(non_zero_tx.sum()) == 0:
        balance_delta = parsed_df["balance"].diff().fillna(0)
        parsed_df["income_amount"] = balance_delta.clip(lower=0)
        parsed_df["expense_amount"] = (-balance_delta).clip(lower=0)
        parsed_df["net_amount"] = parsed_df["income_amount"] - parsed_df["expense_amount"]
        parsed_df["transaction_type"] = parsed_df["net_amount"].apply(lambda x: "Income" if x >= 0 else "Expense")
        non_zero_tx = (parsed_df["income_amount"] > 0) | (parsed_df["expense_amount"] > 0)

    valid_date_rows = len(parsed_df)
    non_zero_rows = int(non_zero_tx.sum())
    parsed_df = parsed_df[non_zero_tx]

    if parsed_df.empty:
        raise ValueError(
            "No valid transactions were found after parsing the statement. "
            f"Rows with valid dates: {valid_date_rows}, rows with non-zero amounts: {non_zero_rows}. "
            "Try selecting the right Amount/Direction columns or Debit/Credit columns. If available, map Balance too for fallback inference."
        )

    return parsed_df


def render_bank_statement_insights(statement_df, statement_currency, display_currency):
    analysis_df = statement_df.copy()
    analysis_df["income_display"] = analysis_df["income_amount"].apply(
        lambda value: convert_currency(value, statement_currency, display_currency)
    )
    analysis_df["expense_display"] = analysis_df["expense_amount"].apply(
        lambda value: convert_currency(value, statement_currency, display_currency)
    )
    analysis_df["net_display"] = analysis_df["income_display"] - analysis_df["expense_display"]
    analysis_df["month"] = analysis_df["date"].dt.to_period("M").astype(str)

    total_income = analysis_df["income_display"].sum()
    total_expenses = analysis_df["expense_display"].sum()
    net_cashflow = total_income - total_expenses
    savings_rate = (net_cashflow / total_income * 100) if total_income > 0 else 0

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("Total Income", format_currency(total_income, display_currency))
    metric_col2.metric("Total Expenses", format_currency(total_expenses, display_currency))
    metric_col3.metric("Net Cashflow", format_currency(net_cashflow, display_currency))
    metric_col4.metric("Savings Rate", f"{savings_rate:.2f}%")

    monthly_summary = analysis_df.groupby("month", as_index=False)[["income_display", "expense_display", "net_display"]].sum()
    trend_fig = go.Figure()
    trend_fig.add_trace(go.Scatter(x=monthly_summary["month"], y=monthly_summary["income_display"], mode="lines+markers", name="Income"))
    trend_fig.add_trace(go.Scatter(x=monthly_summary["month"], y=monthly_summary["expense_display"], mode="lines+markers", name="Expenses"))
    trend_fig.update_layout(title=f"Monthly Income vs Expenses ({display_currency})", xaxis_title="Month", yaxis_title=f"Amount ({display_currency})")
    st.plotly_chart(trend_fig, use_container_width=True)

    expense_breakdown = analysis_df[analysis_df["expense_display"] > 0].groupby("category", as_index=False)["expense_display"].sum()
    if not expense_breakdown.empty:
        expense_breakdown = expense_breakdown.sort_values("expense_display", ascending=False).head(10)
        expense_fig = px.bar(
            expense_breakdown,
            x="expense_display",
            y="category",
            orientation="h",
            title=f"Top Expense Categories ({display_currency})",
            labels={"expense_display": f"Amount ({display_currency})", "category": "Category"}
        )
        st.plotly_chart(expense_fig, use_container_width=True)

    income_breakdown = analysis_df[analysis_df["income_display"] > 0].groupby("category", as_index=False)["income_display"].sum()
    if not income_breakdown.empty:
        income_fig = px.pie(
            income_breakdown,
            values="income_display",
            names="category",
            title=f"Income Distribution by Category ({display_currency})"
        )
        st.plotly_chart(income_fig, use_container_width=True)

    daily_flow = analysis_df.groupby(analysis_df["date"].dt.date, as_index=False)["net_display"].sum()
    daily_flow_fig = px.bar(
        daily_flow,
        x="date",
        y="net_display",
        title=f"Daily Net Cashflow ({display_currency})",
        labels={"date": "Date", "net_display": f"Net Amount ({display_currency})"}
    )
    st.plotly_chart(daily_flow_fig, use_container_width=True)

    st.subheader("Largest Expenses")
    top_expenses = analysis_df[analysis_df["expense_display"] > 0].nlargest(10, "expense_display")[
        ["date", "description", "category", "expense_display"]
    ].copy()
    if not top_expenses.empty:
        top_expenses["expense_display"] = top_expenses["expense_display"].apply(lambda x: format_currency(x, display_currency))
        st.dataframe(top_expenses.rename(columns={"expense_display": "Amount"}), use_container_width=True)
    else:
        st.info("No expense transactions detected in the uploaded statement.")

    st.subheader("Largest Incomes")
    top_incomes = analysis_df[analysis_df["income_display"] > 0].nlargest(10, "income_display")[
        ["date", "description", "category", "income_display"]
    ].copy()
    if not top_incomes.empty:
        top_incomes["income_display"] = top_incomes["income_display"].apply(lambda x: format_currency(x, display_currency))
        st.dataframe(top_incomes.rename(columns={"income_display": "Amount"}), use_container_width=True)
    else:
        st.info("No income transactions detected in the uploaded statement.")


def render_saved_bank_insights(filtered_df, display_currency, selected_banks=None):
    if filtered_df.empty:
        st.info("No bank statement data found for selected filters.")
        return

    insight_df = filtered_df.copy()
    insight_df["income_display"] = insight_df.apply(
        lambda row: convert_currency(row["income_amount"], row["currency"], display_currency),
        axis=1
    )
    insight_df["expense_display"] = insight_df.apply(
        lambda row: convert_currency(row["expense_amount"], row["currency"], display_currency),
        axis=1
    )
    insight_df["net_display"] = insight_df["income_display"] - insight_df["expense_display"]
    insight_df["month"] = pd.to_datetime(insight_df["txn_date"]).dt.to_period("M").astype(str)

    total_income = insight_df["income_display"].sum()
    total_expenses = insight_df["expense_display"].sum()
    net_cashflow = total_income - total_expenses
    savings_rate = (net_cashflow / total_income * 100) if total_income > 0 else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Income", format_currency(total_income, display_currency))
    k2.metric("Total Expenses", format_currency(total_expenses, display_currency))
    k3.metric("Net Cashflow", format_currency(net_cashflow, display_currency))
    k4.metric("Savings Rate", f"{savings_rate:.2f}%")

    bank_summary = insight_df.groupby("bank_name", as_index=False).agg(
        transactions=("id", "count"),
        income_display=("income_display", "sum"),
        expense_display=("expense_display", "sum"),
        net_display=("net_display", "sum")
    )
    if selected_banks:
        base_banks = pd.DataFrame({"bank_name": list(selected_banks)})
        bank_summary = base_banks.merge(bank_summary, on="bank_name", how="left")
        bank_summary[["transactions", "income_display", "expense_display", "net_display"]] = (
            bank_summary[["transactions", "income_display", "expense_display", "net_display"]].fillna(0)
        )

    st.subheader("Bank-Wise Summary")
    bank_summary_display = bank_summary.copy()
    bank_summary_display["transactions"] = bank_summary_display["transactions"].astype(int)
    bank_summary_display["income_display"] = bank_summary_display["income_display"].apply(lambda x: format_currency(x, display_currency))
    bank_summary_display["expense_display"] = bank_summary_display["expense_display"].apply(lambda x: format_currency(x, display_currency))
    bank_summary_display["net_display"] = bank_summary_display["net_display"].apply(lambda x: format_currency(x, display_currency))
    st.dataframe(
        bank_summary_display.rename(columns={
            "bank_name": "Bank",
            "transactions": "Transactions",
            "income_display": "Income",
            "expense_display": "Expense",
            "net_display": "Net"
        }),
        use_container_width=True
    )

    monthly_df = insight_df.groupby(["month", "bank_name"], as_index=False)[["income_display", "expense_display"]].sum()
    income_fig = px.bar(
        monthly_df,
        x="month",
        y="income_display",
        color="bank_name",
        barmode="stack",
        title=f"Monthly Income by Bank ({display_currency})",
        labels={"income_display": f"Income ({display_currency})", "month": "Month", "bank_name": "Bank"}
    )
    st.plotly_chart(income_fig, use_container_width=True)

    expense_fig = px.bar(
        monthly_df,
        x="month",
        y="expense_display",
        color="bank_name",
        barmode="stack",
        title=f"Monthly Expenses by Bank ({display_currency})",
        labels={"expense_display": f"Expenses ({display_currency})", "month": "Month", "bank_name": "Bank"}
    )
    st.plotly_chart(expense_fig, use_container_width=True)

    category_df = insight_df[insight_df["expense_display"] > 0].groupby("category", as_index=False)["expense_display"].sum()
    if not category_df.empty:
        category_df = category_df.sort_values("expense_display", ascending=False).head(12)
        cat_fig = px.bar(
            category_df,
            x="expense_display",
            y="category",
            orientation="h",
            title=f"Top Expense Categories ({display_currency})",
            labels={"expense_display": f"Amount ({display_currency})", "category": "Category"}
        )
        st.plotly_chart(cat_fig, use_container_width=True)

    st.subheader("Filtered Transactions")
    tx_df = insight_df[["txn_date", "bank_name", "description", "category", "income_display", "expense_display", "net_display"]].copy()
    tx_df["income_display"] = tx_df["income_display"].apply(lambda x: format_currency(x, display_currency))
    tx_df["expense_display"] = tx_df["expense_display"].apply(lambda x: format_currency(x, display_currency))
    tx_df["net_display"] = tx_df["net_display"].apply(lambda x: format_currency(x, display_currency))
    st.dataframe(
        tx_df.rename(columns={"txn_date": "Date", "bank_name": "Bank", "income_display": "Income", "expense_display": "Expense", "net_display": "Net"}),
        use_container_width=True
    )


def maybe_rerun():
    rerun_fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if rerun_fn:
        rerun_fn()
    else:
        st.info("Please refresh the page to apply the latest data.")


def init_session_state():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""
        st.session_state.user_id = ""
        st.session_state.auth_error = ""
        st.session_state.reg_success = ""
        st.session_state.fp_step = 1
        st.session_state.fp_username = ""
        st.session_state.fp_question = ""
    if "selected_page" not in st.session_state:
        st.session_state.selected_page = "Overview"


def logout():
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.user_id = ""
    st.session_state.auth_error = ""
    st.session_state.reg_success = ""
    st.session_state.fp_step = 1
    st.session_state.fp_username = ""
    st.session_state.fp_question = ""


def show_login_form(conn):
    st.title("Finance Dashboard")
    login_tab, register_tab, forgot_tab = st.tabs(["Login", "Create Account", "Forgot Password"])

    # -- LOGIN --------------------------------------------------------------
    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            if submitted:
                user = authenticate_user(conn, username.strip(), password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.username = user['username']
                    st.session_state.role = user['role']
                    st.session_state.user_id = user['username']
                    st.session_state.auth_error = ""
                    st.session_state.reg_success = ""
                    maybe_rerun()
                else:
                    st.session_state.auth_error = "Invalid username or password"
        if st.session_state.get("auth_error"):
            st.error(st.session_state.auth_error)
        if st.session_state.get("reg_success"):
            st.success(st.session_state.reg_success)

    # -- CREATE ACCOUNT -----------------------------------------------------
    with register_tab:
        st.write("Fill in the details below to create your account.")
        with st.form("register_form"):
            r_col1, r_col2 = st.columns(2)
            with r_col1:
                r_first_name = st.text_input("First Name *", key="reg_first")
                r_username   = st.text_input("Username *", key="reg_username",
                                             help="At least 3 characters, used to log in")
                r_password   = st.text_input("Password *", type="password", key="reg_password",
                                             help="Minimum 6 characters")
                r_phone      = st.text_input("Phone Number", key="reg_phone")
            with r_col2:
                r_last_name  = st.text_input("Last Name *", key="reg_last")
                r_email      = st.text_input("Email Address *", key="reg_email")
                r_confirm    = st.text_input("Confirm Password *", type="password", key="reg_confirm")
                r_country    = st.text_input("Country", key="reg_country")

            r_dob = st.date_input("Date of Birth", key="reg_dob",
                                  min_value=dt_date(1900, 1, 1),
                                  max_value=dt_date.today())

            st.markdown("**Security Question** *(used to recover your password)*")
            sq_options = [
                "What was the name of your first pet?",
                "What is your mother's maiden name?",
                "What city were you born in?",
                "What was the name of your primary school?",
                "What is the name of your oldest sibling?",
                "What was your childhood nickname?",
            ]
            r_sq     = st.selectbox("Select a security question *", sq_options, key="reg_sq")
            r_sa     = st.text_input("Your answer *", key="reg_sa",
                                     help="Answer is case-insensitive")

            reg_submitted = st.form_submit_button("Create Account")
            if reg_submitted:
                if r_password != r_confirm:
                    st.error("Passwords do not match.")
                else:
                    ok, err = register_user(
                        conn,
                        username=r_username.strip(),
                        password=r_password,
                        first_name=r_first_name,
                        last_name=r_last_name,
                        date_of_birth=str(r_dob),
                        email=r_email,
                        phone=r_phone,
                        country=r_country,
                        security_question=r_sq,
                        security_answer=r_sa,
                    )
                    if ok:
                        st.session_state.reg_success = (
                            f"Account '{r_username.strip()}' created successfully! "
                            "Please log in using the Login tab."
                        )
                        st.session_state.auth_error = ""
                        st.rerun()
                    else:
                        st.error(err)

    # -- FORGOT PASSWORD ----------------------------------------------------
    with forgot_tab:
        st.write("Reset your password by verifying your identity.")
        fp_step = st.session_state.get("fp_step", 1)

        if fp_step == 1:
            with st.form("fp_form1"):
                fp_username = st.text_input("Username", key="fp_username_input")
                fp_next = st.form_submit_button("Next")
                if fp_next:
                    if not fp_username.strip():
                        st.error("Please enter your username.")
                    else:
                        u = get_user(conn, fp_username.strip())
                        if not u or not u.get('security_question'):
                            st.error("Username not found or no security question set.")
                        else:
                            st.session_state.fp_step = 2
                            st.session_state.fp_username = fp_username.strip()
                            st.session_state.fp_question = u['security_question']
                            st.rerun()

        elif fp_step == 2:
            sq = st.session_state.get("fp_question", "")
            st.info(f"Security question: **{sq}**")
            with st.form("fp_form2"):
                fp_answer   = st.text_input("Your answer", key="fp_answer")
                fp_new_pw   = st.text_input("New Password", type="password", key="fp_new_pw",
                                            help="Minimum 6 characters")
                fp_confirm  = st.text_input("Confirm New Password", type="password", key="fp_confirm")
                fp_submit   = st.form_submit_button("Reset Password")
                if fp_submit:
                    fp_user = st.session_state.get("fp_username", "")
                    if fp_new_pw != fp_confirm:
                        st.error("Passwords do not match.")
                    elif len(fp_new_pw) < 6:
                        st.error("Password must be at least 6 characters.")
                    elif not verify_security_answer(conn, fp_user, fp_answer):
                        st.error("Incorrect answer. Please try again.")
                    else:
                        reset_user_password(conn, fp_user, fp_new_pw)
                        st.session_state.fp_step = 1
                        st.session_state.fp_username = ""
                        st.session_state.fp_question = ""
                        st.session_state.reg_success = (
                            "Password reset successfully! You can now log in."
                        )
                        st.rerun()
            if st.button("<- Back", key="fp_back"):
                st.session_state.fp_step = 1
                st.rerun()


def show_profile_editor(conn):
    user = get_user(conn, st.session_state.username)
    if not user:
        st.sidebar.error("Unable to load profile details.")
        return

    dob_raw = str(user.get("date_of_birth") or "").strip()
    if dob_raw:
        try:
            dob_default = datetime.strptime(dob_raw[:10], "%Y-%m-%d").date()
        except ValueError:
            dob_default = dt_date.today()
    else:
        dob_default = dt_date.today()

    sq_options = [
        "What was the name of your first pet?",
        "What is your mother's maiden name?",
        "What city were you born in?",
        "What was the name of your primary school?",
        "What is the name of your oldest sibling?",
        "What was your childhood nickname?",
    ]
    current_sq = (user.get("security_question") or "").strip()
    sq_index = sq_options.index(current_sq) if current_sq in sq_options else 0

    with st.sidebar.expander("My Profile", expanded=False):
        st.caption("Update your personal information.")
        with st.form("profile_update_form"):
            col1, col2 = st.columns(2)
            with col1:
                profile_first_name = st.text_input("First Name", value=user.get("first_name", ""), key="profile_first_name")
                profile_email = st.text_input("Email", value=user.get("email", ""), key="profile_email")
                profile_phone = st.text_input("Phone", value=user.get("phone", ""), key="profile_phone")
            with col2:
                profile_last_name = st.text_input("Last Name", value=user.get("last_name", ""), key="profile_last_name")
                profile_country = st.text_input("Country", value=user.get("country", ""), key="profile_country")

            profile_dob = st.date_input(
                "Date of Birth",
                value=dob_default,
                min_value=dt_date(1900, 1, 1),
                max_value=dt_date.today(),
                key="profile_dob",
            )

            profile_sq = st.selectbox(
                "Security Question",
                sq_options,
                index=sq_index,
                key="profile_sq",
            )
            profile_sa = st.text_input(
                "New Security Answer (optional)",
                key="profile_sa",
                help="Leave blank to keep your existing answer.",
            )

            profile_submit = st.form_submit_button("Save Profile")
            if profile_submit:
                ok, err = update_user_profile(
                    conn,
                    username=st.session_state.username,
                    first_name=profile_first_name,
                    last_name=profile_last_name,
                    date_of_birth=str(profile_dob),
                    email=profile_email,
                    phone=profile_phone,
                    country=profile_country,
                    security_question=profile_sq,
                    security_answer=profile_sa,
                )
                if ok:
                    st.success("Profile updated successfully.")
                else:
                    st.error(err)

import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_URL = os.getenv("DATABASE_URL", "finance.db")  # Use environment variable or default to local file

# Connect to database
conn = create_connection(DB_URL)
if conn:
    create_tables(conn)
    migrate_add_user_id(conn)
    create_users_table(conn)
    insert_default_users(conn)
    # Check if data exists; if not, seed sample data attributed to the admin account
    if pd.read_sql_query("SELECT COUNT(*) FROM income", conn).iloc[0, 0] == 0:
        insert_sample_data(conn, user_id='admin')
else:
    st.error("Failed to connect to database")
    db_err = get_last_connection_error()
    if db_err:
        st.caption(f"Connection details: {db_err}")
    st.info("For Supabase URLs, use an encoded password (for example * becomes %2A) and verify host/port/user from the Supabase connection string page.")
    st.stop()

init_session_state()
logout_clicked = st.sidebar.button("Logout")
if logout_clicked:
    logout()
    show_login_form(conn)
    st.stop()

if not st.session_state.logged_in:
    show_login_form(conn)
    st.stop()

apply_designer_ui()

st.sidebar.title("Filters & Controls")
st.sidebar.write(f"Logged in as **{st.session_state.username}** ({st.session_state.role})")
show_profile_editor(conn)

# Collapsible navigation menu — expands on mouseover
NAV_PAGES = [
    "Overview",
    "Income Tracking",
    "Expenses Tracking",
    "Investments",
    "Fixed Deposits",
    "Real Estate",
    "Fund Allocation",
    "Insights",
    "Filters",
    "Upload",
    "Cash",
    "Bank Statement Loading",
    "Bank Insights",
]

with st.sidebar.expander("☰  Dashboard", expanded=False):
    for _page in NAV_PAGES:
        _active = st.session_state.selected_page == _page
        _label = f"{'▶ ' if _active else '   '}{_page}"
        if st.button(_label, key=f"nav_{_page}", use_container_width=True):
            st.session_state.selected_page = _page
            st.rerun()

# JS: hover-expand the Dashboard nav expander via summary.click() so React registers it
st.sidebar.markdown(
    """
    <script>
    (function() {
        var _leaveTimer = null;

        function attachHover(d) {
            if (d._navHoverAttached) return;
            d._navHoverAttached = true;

            var summary = d.querySelector('summary');
            if (!summary) return;

            d.addEventListener('mouseenter', function() {
                if (_leaveTimer) { clearTimeout(_leaveTimer); _leaveTimer = null; }
                if (!d.hasAttribute('open')) {
                    summary.click();
                }
            });

            d.addEventListener('mouseleave', function() {
                _leaveTimer = setTimeout(function() {
                    if (d.hasAttribute('open')) {
                        summary.click();
                    }
                }, 400);
            });
        }

        function findAndAttach() {
            var details = document.querySelectorAll('[data-testid="stSidebar"] details');
            details.forEach(function(d) {
                var s = d.querySelector('summary');
                if (s && s.textContent && s.textContent.indexOf('Dashboard') >= 0) {
                    attachHover(d);
                }
            });
        }

        // Run immediately and watch for Streamlit re-renders
        findAndAttach();
        var obs = new MutationObserver(findAndAttach);
        obs.observe(document.body, { childList: true, subtree: true });
    })();
    </script>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown("---")

# Admin: optionally view all users' data or a specific user's data
is_admin = st.session_state.role == "admin"
if is_admin:
    all_usernames = get_all_usernames(conn)
    view_as_options = ["All Users"] + all_usernames
    view_as = st.sidebar.selectbox("View Data As", view_as_options, index=0)
    user_id = None if view_as == "All Users" else view_as
else:
    user_id = st.session_state.user_id

mode = st.sidebar.radio("Mode", ["Personal", "Business"])
account_type = mode.lower()
period = st.sidebar.selectbox("Time Period", ["Monthly", "Yearly", "All"], index=0)
category_filter = st.sidebar.selectbox("Category Filter", ["All", "Income", "Expenses", "Investments", "Fixed Deposits", "Real Estate"], index=0)
display_currency = st.sidebar.selectbox("Display Currency", ["USD", "EUR", "INR"], index=0)

selected_page = st.session_state.selected_page

# Main title
st.title("Personal Finance Dashboard")

if selected_page == "Overview":
    st.header(f"{mode} Overview")
    col1, col2, col3, col4 = st.columns(4)
    net_worth = calculate_net_worth(conn, account_type, user_id=user_id)
    income, expenses, savings_rate = calculate_income_expenses(conn, period.lower(), account_type, user_id=user_id)
    
    # Convert to display currency (assuming calculations are in USD)
    net_worth_display = convert_currency(net_worth, 'USD', display_currency)
    income_display = convert_currency(income, 'USD', display_currency)
    expenses_display = convert_currency(expenses, 'USD', display_currency)
    
    with col1:
        st.metric("Net Worth", format_currency(net_worth_display, display_currency))
    with col2:
        st.metric("Monthly Income", format_currency(income_display, display_currency))
    with col3:
        st.metric("Monthly Expenses", format_currency(expenses_display, display_currency))
    with col4:
        st.metric("Savings Rate", f"{savings_rate:.2f}%")

if selected_page == "Income Tracking":
    st.header(f"{mode} Income Tracking")
    income_df = get_data(conn, "income", account_type=account_type, user_id=user_id)
    if not income_df.empty:
        income_df['date'] = pd.to_datetime(income_df['date'])
        income_df['month'] = income_df['date'].dt.to_period('M')
        # Convert amounts to display currency
        income_df['amount_display'] = income_df.apply(lambda x: convert_currency(x['amount'], x['currency'], display_currency), axis=1)
        monthly_income = income_df.groupby('month')['amount_display'].sum().reset_index()
        monthly_income['month'] = monthly_income['month'].astype(str)
        
        fig = px.line(monthly_income, x='month', y='amount_display', title=f"Monthly Income Trend ({display_currency})")
        st.plotly_chart(fig)
        
        st.subheader("Income Sources")
        source_df = income_df.copy()
        source_df['amount_display'] = source_df.apply(lambda x: convert_currency(x['amount'], x['currency'], display_currency), axis=1)
        source_summary = source_df.groupby('source')['amount_display'].sum().reset_index()
        fig2 = px.bar(source_summary, x='source', y='amount_display', title=f"Income by Source ({display_currency})")
        st.plotly_chart(fig2)
        
        st.subheader("Income Details")
        display_df = income_df.copy()
        display_df['amount_display'] = display_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
        st.dataframe(display_df[['date', 'source', 'amount_display', 'currency', 'type']].rename(columns={
            'amount_display': 'Amount',
            'type': 'Income Type'
        }))
        
        # Summary metrics
        total_income = sum(convert_currency(row['amount'], row['currency'], display_currency) for _, row in income_df.iterrows())
        avg_monthly = total_income / len(monthly_income) if len(monthly_income) > 0 else 0
        st.metric("Total Income", format_currency(total_income, display_currency))
        st.metric("Average Monthly Income", format_currency(avg_monthly, display_currency))
    else:
        st.write("No income data available")

if selected_page == "Expenses Tracking":
    st.header(f"{mode} Expenses Tracking")
    expenses_df = get_data(conn, "expenses", account_type=account_type, user_id=user_id)
    if not expenses_df.empty:
        expenses_df['date'] = pd.to_datetime(expenses_df['date'])
        expenses_df['month'] = expenses_df['date'].dt.to_period('M')
        # Convert amounts to display currency
        expenses_df['amount_display'] = expenses_df.apply(lambda x: convert_currency(x['amount'], x['currency'], display_currency), axis=1)
        monthly_expenses = expenses_df.groupby('month')['amount_display'].sum().reset_index()
        monthly_expenses['month'] = monthly_expenses['month'].astype(str)
        
        fig = px.line(monthly_expenses, x='month', y='amount_display', title=f"Monthly Expenses Trend ({display_currency})")
        st.plotly_chart(fig)
        
        st.subheader("Expenses by Category")
        category_df = expenses_df.copy()
        category_df['amount_display'] = category_df.apply(lambda x: convert_currency(x['amount'], x['currency'], display_currency), axis=1)
        category_summary = category_df.groupby('category')['amount_display'].sum().reset_index()
        fig2 = px.bar(category_summary, x='category', y='amount_display', title=f"Expenses by Category ({display_currency})")
        st.plotly_chart(fig2)
        
        st.subheader("Expense Details")
        display_df = expenses_df.copy()
        display_df['amount_display'] = display_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
        st.dataframe(display_df[['date', 'category', 'amount_display', 'currency']].rename(columns={
            'amount_display': 'Amount'
        }))
        
        # Summary metrics
        total_expenses = sum(convert_currency(row['amount'], row['currency'], display_currency) for _, row in expenses_df.iterrows())
        avg_monthly = total_expenses / len(monthly_expenses) if len(monthly_expenses) > 0 else 0
        st.metric("Total Expenses", format_currency(total_expenses, display_currency))
        st.metric("Average Monthly Expenses", format_currency(avg_monthly, display_currency))
    else:
        st.write("No expenses data available")

if selected_page == "Investments":
    st.header(f"{mode} Investments")
    inv_df = get_data(conn, "investments", account_type=account_type, user_id=user_id)
    if not inv_df.empty:
        inv_df['profit_loss'] = inv_df['current_value'] - inv_df['invested_amount']
        display_df = inv_df.copy()
        display_df['invested_amount'] = display_df.apply(lambda x: convert_currency(x['invested_amount'], x['currency'], display_currency), axis=1)
        display_df['current_value'] = display_df.apply(lambda x: convert_currency(x['current_value'], x['currency'], display_currency), axis=1)
        display_df['profit_loss'] = display_df.apply(lambda x: convert_currency(x['profit_loss'], x['currency'], display_currency), axis=1)
        display_df['invested_amount'] = display_df.apply(lambda x: format_currency(x['invested_amount'], display_currency), axis=1)
        display_df['current_value'] = display_df.apply(lambda x: format_currency(x['current_value'], display_currency), axis=1)
        display_df['profit_loss'] = display_df.apply(lambda x: format_currency(x['profit_loss'], display_currency) if x['profit_loss'] >= 0 else f"-{format_currency(-x['profit_loss'], display_currency)}", axis=1)
        st.dataframe(display_df[['category', 'name', 'invested_amount', 'current_value', 'profit_loss', 'currency']])
        
        # Pie chart for allocation - convert to display currency
        allocation_df = inv_df.copy()
        allocation_df['current_value'] = allocation_df.apply(lambda x: convert_currency(x['current_value'], x['currency'], display_currency), axis=1)
        allocation = allocation_df.groupby('category')['current_value'].sum().reset_index()
        fig = px.pie(allocation, values='current_value', names='category', title=f"Portfolio Allocation ({display_currency})")
        st.plotly_chart(fig)
        
        # Performance over time
        inv_df['date_purchased'] = pd.to_datetime(inv_df['date_purchased'])
        inv_df['months'] = (datetime.now() - inv_df['date_purchased']).dt.days / 30
        inv_df['profit_loss_display'] = inv_df.apply(lambda x: convert_currency(x['profit_loss'], x['currency'], display_currency), axis=1)
        fig2 = px.scatter(inv_df, x='months', y='profit_loss_display', color='category', title=f"Performance Over Time ({display_currency})")
        st.plotly_chart(fig2)

if selected_page == "Fixed Deposits":
    st.header(f"{mode} Fixed Deposits")
    fd_df = get_data(conn, "fixed_deposits", account_type=account_type, user_id=user_id)
    if not fd_df.empty:
        display_df = fd_df.copy()
        display_df['principal'] = display_df.apply(lambda x: convert_currency(x['principal'], x['currency'], display_currency), axis=1)
        display_df['maturity_value'] = display_df.apply(lambda x: convert_currency(x['maturity_value'], x['currency'], display_currency), axis=1)
        display_df['principal'] = display_df.apply(lambda x: format_currency(x['principal'], display_currency), axis=1)
        display_df['maturity_value'] = display_df.apply(lambda x: format_currency(x['maturity_value'], display_currency), axis=1)
        st.dataframe(display_df[['bank', 'principal', 'interest_rate', 'maturity_date', 'maturity_value', 'currency']])
        
        total_fd = sum(convert_currency(row['maturity_value'], row['currency'], display_currency) for _, row in fd_df.iterrows())
        st.metric("Total FD Allocation", format_currency(total_fd, display_currency))
        
        # Upcoming maturities
        fd_df['maturity_date'] = pd.to_datetime(fd_df['maturity_date'])
        upcoming = fd_df[fd_df['maturity_date'] > datetime.now()].sort_values('maturity_date')
        if not upcoming.empty:
            upcoming_display = upcoming.copy()
            upcoming_display['maturity_value_display'] = upcoming_display.apply(lambda x: convert_currency(x['maturity_value'], x['currency'], display_currency), axis=1)
            upcoming_display['maturity_value_display'] = upcoming_display['maturity_value_display'].apply(lambda x: format_currency(x, display_currency))
            st.subheader("Upcoming Maturities")
            st.dataframe(upcoming_display[['bank', 'maturity_date', 'maturity_value_display', 'currency']])

if selected_page == "Real Estate":
    st.header(f"{mode} Real Estate")
    re_df = get_data(conn, "real_estate", account_type=account_type, user_id=user_id)
    if not re_df.empty:
        re_df['roi'] = ((re_df['current_value'] - re_df['purchase_price']) / re_df['purchase_price']) * 100
        display_df = re_df.copy()
        display_df['purchase_price'] = display_df.apply(lambda x: convert_currency(x['purchase_price'], x['currency'], display_currency), axis=1)
        display_df['current_value'] = display_df.apply(lambda x: convert_currency(x['current_value'], x['currency'], display_currency), axis=1)
        display_df['rental_income'] = display_df.apply(lambda x: convert_currency(x['rental_income'], x['currency'], display_currency), axis=1)
        display_df['purchase_price'] = display_df.apply(lambda x: format_currency(x['purchase_price'], display_currency), axis=1)
        display_df['current_value'] = display_df.apply(lambda x: format_currency(x['current_value'], display_currency), axis=1)
        display_df['rental_income'] = display_df.apply(lambda x: format_currency(x['rental_income'], display_currency), axis=1)
        st.dataframe(display_df[['property_name', 'purchase_price', 'current_value', 'rental_income', 'roi', 'currency']])
        
        total_value = sum(convert_currency(row['current_value'], row['currency'], display_currency) for _, row in re_df.iterrows())
        total_income = sum(convert_currency(row['rental_income'], row['currency'], display_currency) for _, row in re_df.iterrows())
        st.metric("Total Real Estate Value", format_currency(total_value, display_currency))
        st.metric("Total Rental Income", format_currency(total_income, display_currency))

if selected_page == "Fund Allocation":
    st.header(f"{mode} Fund Allocation")
    # Calculate allocations
    inv_df = get_data(conn, "investments", account_type=account_type, user_id=user_id)
    fd_df = get_data(conn, "fixed_deposits", account_type=account_type, user_id=user_id)
    re_df = get_data(conn, "real_estate", account_type=account_type, user_id=user_id)
    cash_df = get_data(conn, "cash", account_type=account_type, user_id=user_id)
    income_df = get_data(conn, "income", account_type=account_type, user_id=user_id)
    expenses_df = get_data(conn, "expenses", account_type=account_type, user_id=user_id)
    
    inv_total = sum(convert_currency(row['current_value'], row['currency'], display_currency) for _, row in inv_df.iterrows()) if not inv_df.empty else 0
    fd_total = sum(convert_currency(row['maturity_value'], row['currency'], display_currency) for _, row in fd_df.iterrows()) if not fd_df.empty else 0
    re_total = sum(convert_currency(row['current_value'], row['currency'], display_currency) for _, row in re_df.iterrows()) if not re_df.empty else 0
    cash_total = sum(convert_currency(row['amount'], row['currency'], display_currency) for _, row in cash_df.iterrows()) if not cash_df.empty else 0
    income_total = sum(convert_currency(row['amount'], row['currency'], display_currency) for _, row in income_df.iterrows()) if not income_df.empty else 0
    expenses_total = sum(convert_currency(row['amount'], row['currency'], display_currency) for _, row in expenses_df.iterrows()) if not expenses_df.empty else 0
    
    allocations = {
        'Investments': inv_total,
        'Fixed Deposits': fd_total,
        'Real Estate': re_total,
        'Cash': cash_total,
        'Income': income_total,
        'Expenses': expenses_total
    }
    
    fig = px.pie(values=list(allocations.values()), names=list(allocations.keys()), title=f"Fund Allocation ({display_currency})")
    st.plotly_chart(fig)

if selected_page == "Insights":
    st.header(f"{mode} Insights & Analytics")
    # Simple insights
    income, expenses, savings_rate = calculate_income_expenses(conn, 'monthly', account_type, user_id=user_id)
    if savings_rate < 20:
        st.warning("Savings rate is below 20%. Consider reducing expenses or increasing income.")
    else:
        st.success("Good savings rate!")
    
    # Trends
    income_df = get_data(conn, "income", account_type=account_type, user_id=user_id)
    expenses_df = get_data(conn, "expenses", account_type=account_type, user_id=user_id)
    if not income_df.empty and not expenses_df.empty:
        income_df['date'] = pd.to_datetime(income_df['date'])
        expenses_df['date'] = pd.to_datetime(expenses_df['date'])
        income_df['amount_usd'] = income_df.apply(lambda x: convert_currency(x['amount'], x['currency'], 'USD'), axis=1)
        expenses_df['amount_usd'] = expenses_df.apply(lambda x: convert_currency(x['amount'], x['currency'], 'USD'), axis=1)
        income_trend = income_df.groupby(income_df['date'].dt.month)['amount_usd'].sum()
        expenses_trend = expenses_df.groupby(expenses_df['date'].dt.month)['amount_usd'].sum()
        
        # Convert to display currency for chart
        income_trend_display = income_trend.apply(lambda x: convert_currency(x, 'USD', display_currency))
        expenses_trend_display = expenses_trend.apply(lambda x: convert_currency(x, 'USD', display_currency))
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=income_trend_display.index, y=income_trend_display.values, mode='lines', name='Income'))
        fig.add_trace(go.Scatter(x=expenses_trend_display.index, y=expenses_trend_display.values, mode='lines', name='Expenses'))
        fig.update_layout(title=f"Income vs Expenses Trend ({display_currency})")
        st.plotly_chart(fig)

if selected_page == "Filters":
    st.header(f"{mode} Filters & Data View")
    
    # Apply filters
    if category_filter == "All":
        # Show all data
        st.subheader("All Financial Data")
        all_data = []
        
        income_df = get_data(conn, "income", account_type=account_type, user_id=user_id)
        if not income_df.empty:
            income_df['type'] = 'Income'
            income_df['amount_display'] = income_df.apply(lambda x: convert_currency(x['amount'], x['currency'], display_currency), axis=1)
            income_df['amount_display'] = income_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            all_data.append(income_df[['date', 'type', 'source', 'amount_display', 'currency']])
        
        expenses_df = get_data(conn, "expenses", account_type=account_type, user_id=user_id)
        if not expenses_df.empty:
            expenses_df['type'] = 'Expense'
            expenses_df['amount_display'] = expenses_df.apply(lambda x: convert_currency(x['amount'], x['currency'], display_currency), axis=1)
            expenses_df['amount_display'] = expenses_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            all_data.append(expenses_df[['date', 'type', 'category', 'amount_display', 'currency']])
        
        investments_df = get_data(conn, "investments", account_type=account_type, user_id=user_id)
        if not investments_df.empty:
            investments_df['type'] = 'Investment'
            investments_df['amount_display'] = investments_df.apply(lambda x: convert_currency(x['current_value'], x['currency'], display_currency), axis=1)
            investments_df['amount_display'] = investments_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            all_data.append(investments_df[['date_purchased', 'type', 'name', 'amount_display', 'currency']])
        
        fd_df = get_data(conn, "fixed_deposits", account_type=account_type, user_id=user_id)
        if not fd_df.empty:
            fd_df['type'] = 'Fixed Deposit'
            fd_df['amount_display'] = fd_df.apply(lambda x: convert_currency(x['maturity_value'], x['currency'], display_currency), axis=1)
            fd_df['amount_display'] = fd_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            all_data.append(fd_df[['maturity_date', 'type', 'bank', 'amount_display', 'currency']])
        
        re_df = get_data(conn, "real_estate", account_type=account_type, user_id=user_id)
        if not re_df.empty:
            re_df['type'] = 'Real Estate'
            re_df['amount_display'] = re_df.apply(lambda x: convert_currency(x['current_value'], x['currency'], display_currency), axis=1)
            re_df['amount_display'] = re_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            all_data.append(re_df[['property_name', 'type', 'purchase_price', 'amount_display', 'currency']])
        
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            st.dataframe(combined_df)
        else:
            st.write("No data available")
    
    elif category_filter == "Income":
        st.subheader("Income Data")
        income_df = get_data(conn, "income", account_type=account_type, user_id=user_id)
        if not income_df.empty:
            income_df['amount_display'] = income_df.apply(lambda x: convert_currency(x['amount'], x['currency'], display_currency), axis=1)
            income_df['amount_display'] = income_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            st.dataframe(income_df[['date', 'source', 'amount_display', 'currency', 'type']])
            
            # Pie chart for income by source
            source_summary = income_df.groupby('source')['amount_display'].sum().reset_index()
            fig = px.pie(source_summary, values='amount_display', names='source', title=f"Income by Source ({display_currency})")
            st.plotly_chart(fig)
        else:
            st.write("No income data available")
    
    elif category_filter == "Expenses":
        st.subheader("Expenses Data")
        expenses_df = get_data(conn, "expenses", account_type=account_type, user_id=user_id)
        if not expenses_df.empty:
            expenses_df['amount_display'] = expenses_df.apply(lambda x: convert_currency(x['amount'], x['currency'], display_currency), axis=1)
            expenses_df['amount_display'] = expenses_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            st.dataframe(expenses_df[['date', 'category', 'amount_display', 'currency']])
            
            # Pie chart for expenses by category
            category_summary = expenses_df.groupby('category')['amount_display'].sum().reset_index()
            fig = px.pie(category_summary, values='amount_display', names='category', title=f"Expenses by Category ({display_currency})")
            st.plotly_chart(fig)
        else:
            st.write("No expenses data available")
    
    elif category_filter == "Investments":
        st.subheader("Investments Data")
        inv_df = get_data(conn, "investments", account_type=account_type, user_id=user_id)
        if not inv_df.empty:
            inv_df['amount_display'] = inv_df.apply(lambda x: convert_currency(x['current_value'], x['currency'], display_currency), axis=1)
            inv_df['amount_display'] = inv_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            st.dataframe(inv_df[['date_purchased', 'category', 'name', 'amount_display', 'currency']])
            
            # Bar chart for investments by category
            category_summary = inv_df.groupby('category')['amount_display'].sum().reset_index()
            fig = px.bar(category_summary, x='category', y='amount_display', title=f"Investments by Category ({display_currency})")
            st.plotly_chart(fig)
        else:
            st.write("No investments data available")
    
    elif category_filter == "Fixed Deposits":
        st.subheader("Fixed Deposits Data")
        fd_df = get_data(conn, "fixed_deposits", account_type=account_type, user_id=user_id)
        if not fd_df.empty:
            fd_df['amount_display'] = fd_df.apply(lambda x: convert_currency(x['maturity_value'], x['currency'], display_currency), axis=1)
            fd_df['amount_display'] = fd_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            st.dataframe(fd_df[['maturity_date', 'bank', 'amount_display', 'currency']])
        else:
            st.write("No fixed deposits data available")
    
    elif category_filter == "Real Estate":
        st.subheader("Real Estate Data")
        re_df = get_data(conn, "real_estate", account_type=account_type, user_id=user_id)
        if not re_df.empty:
            re_df['amount_display'] = re_df.apply(lambda x: convert_currency(x['current_value'], x['currency'], display_currency), axis=1)
            re_df['amount_display'] = re_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            st.dataframe(re_df[['property_name', 'purchase_price', 'amount_display', 'currency']])
        else:
            st.write("No real estate data available")

if selected_page == "Upload":
    st.header("Bulk Excel Upload")
    st.write("Upload a `.xlsx` workbook with sheets named `income`, `expenses`, `investments`, `fixed_deposits`, `real_estate`, and `cash`.")
    st.markdown("**Required columns per sheet:**")
    st.markdown(
        "- `income`: source, amount, currency, date, type, account_type<br>"
        "- `expenses`: category, amount, currency, date, account_type<br>"
        "- `investments`: category, name, invested_amount, current_value, currency, date_purchased, account_type<br>"
        "- `fixed_deposits`: bank, principal, interest_rate, maturity_date, maturity_value, currency, account_type<br>"
        "- `real_estate`: property_name, purchase_price, current_value, rental_income, currency, account_type<br>"
        "- `cash`: amount, currency, date, account_type",
        unsafe_allow_html=True,
    )

    upload_file = st.file_uploader("Upload Excel workbook", type=["xlsx"] )
    import_mode = st.radio("Import mode", ["Append", "Replace"], index=0, horizontal=True)
    if upload_file:
        if st.button("Import data from Excel"):
            try:
                validate_upload(upload_file, max_mb=10)
                inserted = import_excel_to_db(conn, upload_file, behavior=import_mode.lower(), user_id=st.session_state.user_id)
                for table_name, count in inserted:
                    st.success(f"Imported {count} rows into {table_name}.")
                maybe_rerun()
            except Exception as exc:
                st.error(f"Upload failed: {exc}")

    st.markdown("---")
    st.subheader("Download existing data")
    try:
        # Admins can download all data; regular users download only their own
        if is_admin:
            export_bytes = export_db_to_excel(conn)
            download_label = "Download all data as Excel"
        else:
            export_bytes = export_db_to_excel(conn, account_type=account_type, user_id=st.session_state.user_id)
            download_label = "Download my data as Excel"
        st.download_button(
            label=download_label,
            data=export_bytes,
            file_name="finance_data_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as exc:
        st.error(f"Unable to create export file: {exc}")

if selected_page == "Cash":
    st.header(f"{mode} Cash Holdings")
    cash_df = get_data(conn, "cash", account_type=account_type, user_id=user_id)
    if not cash_df.empty:
        display_df = cash_df.copy()
        display_df['amount_display'] = display_df.apply(lambda x: convert_currency(x['amount'], x['currency'], display_currency), axis=1)
        display_df['amount_formatted'] = display_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
        st.dataframe(display_df[['date', 'amount_formatted', 'currency']])
        
        # Summary metrics
        total_cash = sum(convert_currency(row['amount'], row['currency'], display_currency) for _, row in cash_df.iterrows())
        st.metric(f"Total Cash ({display_currency})", format_currency(total_cash, display_currency))
    else:
        st.write("No cash data available")

if selected_page == "Bank Statement Loading":
    st.header("Bank Statement Loading")
    st.write("Load a complete bank statement file, review full data, map columns, validate, and save to the database table.")

    bank_name = st.text_input("Bank Name", placeholder="e.g. HDFC, SBI, ICICI", key="bs_bank_name")

    statement_currency = st.selectbox(
        "Statement Currency",
        ["USD", "EUR", "INR"],
        index=["USD", "EUR", "INR"].index(display_currency),
        key="statement_currency"
    )
    statement_file = st.file_uploader(
        "Upload bank statement (CSV, Excel, or PDF)",
        type=["csv", "xlsx", "xls", "pdf"],
        key="bank_statement_uploader"
    )

    if statement_file:
        try:
            validate_upload(statement_file, max_mb=20)
            loaded_sources = load_bank_statement_sources(statement_file)
            source_name = st.selectbox("Select sheet/table to analyze", list(loaded_sources.keys()), key="statement_source_selector")
            source_df = loaded_sources[source_name].copy()
            source_df.columns = [normalize_column_name(col) for col in source_df.columns]

            st.subheader("Loaded Complete Dataset")
            st.dataframe(source_df, use_container_width=True)

            selectable_columns = [""] + list(source_df.columns)
            suggested_mapping = suggest_bank_statement_mapping(source_df.columns)

            def get_index(options, value):
                return options.index(value) if value in options else 0

            mapping_col1, mapping_col2 = st.columns(2)
            with mapping_col1:
                selected_date_col = st.selectbox(
                    "Date column",
                    selectable_columns,
                    index=get_index(selectable_columns, suggested_mapping["date"]),
                    key="statement_date_col"
                )
                selected_description_col = st.selectbox(
                    "Description column",
                    selectable_columns,
                    index=get_index(selectable_columns, suggested_mapping["description"]),
                    key="statement_description_col"
                )
                selected_amount_col = st.selectbox(
                    "Signed amount column (optional)",
                    selectable_columns,
                    index=get_index(selectable_columns, suggested_mapping["amount"]),
                    key="statement_amount_col"
                )
            with mapping_col2:
                selected_debit_col = st.selectbox(
                    "Debit column (optional)",
                    selectable_columns,
                    index=get_index(selectable_columns, suggested_mapping["debit"]),
                    key="statement_debit_col"
                )
                selected_credit_col = st.selectbox(
                    "Credit column (optional)",
                    selectable_columns,
                    index=get_index(selectable_columns, suggested_mapping["credit"]),
                    key="statement_credit_col"
                )
                selected_direction_col = st.selectbox(
                    "Direction column (optional: CR/DR)",
                    selectable_columns,
                    index=get_index(selectable_columns, suggested_mapping["direction"]),
                    key="statement_direction_col"
                )
                selected_balance_col = st.selectbox(
                    "Balance column (optional)",
                    selectable_columns,
                    index=get_index(selectable_columns, suggested_mapping["balance"]),
                    key="statement_balance_col"
                )

            if st.button("Analyze selected columns", key="analyze_statement_columns"):
                column_mapping = {
                    "date": selected_date_col or None,
                    "description": selected_description_col or None,
                    "amount": selected_amount_col or None,
                    "debit": selected_debit_col or None,
                    "credit": selected_credit_col or None,
                    "direction": selected_direction_col or None,
                    "balance": selected_balance_col or None,
                }

                statement_df = normalize_bank_statement(source_df, column_mapping)
                st.session_state["parsed_bank_statement_df"] = statement_df
                st.session_state["parsed_bank_statement_source"] = source_name
                st.session_state["parsed_bank_statement_currency"] = statement_currency

            if "parsed_bank_statement_df" in st.session_state:
                statement_df = st.session_state["parsed_bank_statement_df"].copy()
                parsed_source = st.session_state.get("parsed_bank_statement_source", "selected source")
                st.success(f"Validated {len(statement_df)} transactions successfully from {parsed_source}.")

                total_loaded_rows = len(source_df)
                valid_rows = len(statement_df)
                dropped_rows = max(total_loaded_rows - valid_rows, 0)
                m1, m2, m3 = st.columns(3)
                m1.metric("Loaded Rows", total_loaded_rows)
                m2.metric("Valid Parsed Rows", valid_rows)
                m3.metric("Dropped Rows", dropped_rows)

                st.subheader("Edit Categories Before Saving")
                editable_preview_df = statement_df[["date", "description", "category", "income_amount", "expense_amount", "net_amount"]].copy()
                edited_preview_df = st.data_editor(
                    editable_preview_df,
                    key="bank_statement_category_editor",
                    use_container_width=True,
                    hide_index=True,
                    disabled=["date", "description", "income_amount", "expense_amount", "net_amount"],
                    column_config={
                        "date": st.column_config.DateColumn("Date"),
                        "description": st.column_config.TextColumn("Description"),
                        "category": st.column_config.TextColumn("Category"),
                        "income_amount": st.column_config.NumberColumn("Income", format="%.2f"),
                        "expense_amount": st.column_config.NumberColumn("Expense", format="%.2f"),
                        "net_amount": st.column_config.NumberColumn("Net", format="%.2f")
                    }
                )
                statement_df["category"] = edited_preview_df["category"].fillna("Other").astype(str).str.strip().replace("", "Other")
                st.session_state["parsed_bank_statement_df"] = statement_df

                st.subheader("Normalized Preview")
                preview_df = statement_df[["date", "description", "category", "income_amount", "expense_amount", "net_amount"]].copy()
                preview_df["income_amount"] = preview_df["income_amount"].apply(lambda x: format_currency(convert_currency(x, st.session_state["parsed_bank_statement_currency"], display_currency), display_currency))
                preview_df["expense_amount"] = preview_df["expense_amount"].apply(lambda x: format_currency(convert_currency(x, st.session_state["parsed_bank_statement_currency"], display_currency), display_currency))
                preview_df["net_amount"] = preview_df["net_amount"].apply(lambda x: format_currency(convert_currency(x, st.session_state["parsed_bank_statement_currency"], display_currency), display_currency))
                st.dataframe(
                    preview_df.rename(columns={
                        "income_amount": "Income",
                        "expense_amount": "Expense",
                        "net_amount": "Net"
                    }),
                    use_container_width=True
                )

                replace_existing = st.checkbox("Replace existing saved rows for this bank and mode", value=False, key="bs_replace_existing")
                if st.button("Save to Bank Statement Table", key="save_bank_statement_table"):
                    if not bank_name.strip():
                        st.warning("Please enter Bank Name before saving.")
                    else:
                        inserted_count = save_bank_statement_rows(
                            conn=conn,
                            bank_name=bank_name.strip(),
                            source_name=st.session_state.get("parsed_bank_statement_source", source_name),
                            currency=st.session_state["parsed_bank_statement_currency"],
                            account_type=account_type,
                            parsed_df=statement_df,
                            replace_existing=replace_existing,
                            user_id=st.session_state.user_id
                        )
                        st.success(f"Saved {inserted_count} rows to bank_statements table for '{bank_name.strip()}' ({account_type}).")
        except Exception as exc:
            st.error(f"Unable to analyze bank statement: {exc}")

if selected_page == "Bank Insights":
    st.header("Bank Insights")
    st.write("Filter and analyze bank statement rows saved in the database table.")

    saved_df = get_bank_statement_data(conn, account_type=account_type, user_id=user_id)
    if saved_df.empty:
        st.info("No saved bank statement rows found for this mode. Use the Bank Statement Loading tab to save data first.")
    else:
        saved_df["bank_name"] = saved_df["bank_name"].fillna("").astype(str).str.strip()
        saved_df = saved_df[saved_df["bank_name"] != ""]
        saved_df["txn_date"] = pd.to_datetime(saved_df["txn_date"], errors="coerce")
        saved_df = saved_df.dropna(subset=["txn_date"])

        bank_options = sorted(saved_df["bank_name"].dropna().unique().tolist())
        selected_banks = st.multiselect("Bank Filter", bank_options, default=bank_options)

        min_date = saved_df["txn_date"].min().date()
        max_date = saved_df["txn_date"].max().date()
        d1, d2 = st.columns(2)
        with d1:
            start_date = st.date_input("Start Date", value=min_date, min_value=min_date, max_value=max_date)
        with d2:
            end_date = st.date_input("End Date", value=max_date, min_value=min_date, max_value=max_date)

        if start_date > end_date:
            st.warning("Start Date is after End Date. Dates were swapped automatically.")
            start_date, end_date = end_date, start_date

        category_options = sorted(saved_df["category"].dropna().unique().tolist())
        selected_categories = st.multiselect("Category Filter", category_options, default=category_options)

        tx_type = st.selectbox("Transaction Type", ["All", "Income", "Expense"], index=0)
        search_text = st.text_input("Description Contains", value="").strip().lower()

        filtered_df = saved_df.copy()
        if selected_banks:
            filtered_df = filtered_df[filtered_df["bank_name"].isin(selected_banks)]

        txn_dates = filtered_df["txn_date"].dt.date
        filtered_df = filtered_df[(txn_dates >= start_date) & (txn_dates <= end_date)]

        if selected_categories:
            filtered_df = filtered_df[filtered_df["category"].isin(selected_categories)]

        if tx_type == "Income":
            filtered_df = filtered_df[filtered_df["income_amount"] > 0]
        elif tx_type == "Expense":
            filtered_df = filtered_df[filtered_df["expense_amount"] > 0]

        if search_text:
            filtered_df = filtered_df[filtered_df["description"].fillna("").str.lower().str.contains(search_text, regex=False)]

        filtered_bank_count = filtered_df["bank_name"].nunique() if not filtered_df.empty else 0
        st.caption(
            f"Filtered rows: {len(filtered_df)} | Banks in result: {filtered_bank_count}"
        )

        with st.expander("Edit Categories After Saving", expanded=False):
            if filtered_df.empty:
                st.info("No rows available for category editing under the current filters.")
            else:
                editable_saved_df = filtered_df[[
                    "id", "txn_date", "bank_name", "description", "income_amount", "expense_amount", "currency", "category"
                ]].copy()
                edited_saved_df = st.data_editor(
                    editable_saved_df,
                    key="saved_bank_statement_category_editor",
                    use_container_width=True,
                    hide_index=True,
                    disabled=["id", "txn_date", "bank_name", "description", "income_amount", "expense_amount", "currency"],
                    column_config={
                        "id": st.column_config.NumberColumn("ID", format="%d"),
                        "txn_date": st.column_config.DateColumn("Date"),
                        "bank_name": st.column_config.TextColumn("Bank"),
                        "description": st.column_config.TextColumn("Description"),
                        "income_amount": st.column_config.NumberColumn("Income", format="%.2f"),
                        "expense_amount": st.column_config.NumberColumn("Expense", format="%.2f"),
                        "currency": st.column_config.TextColumn("Currency"),
                        "category": st.column_config.TextColumn("Category")
                    }
                )

                if st.button("Save Category Changes", key="save_saved_bank_category_changes"):
                    updates = []
                    original_categories = filtered_df.set_index("id")["category"].fillna("Other").astype(str)
                    for _, row in edited_saved_df.iterrows():
                        row_id = int(row["id"])
                        new_category = str(row.get("category", "Other") or "Other").strip() or "Other"
                        if new_category != original_categories.get(row_id, "Other"):
                            updates.append((row_id, new_category))

                    if not updates:
                        st.info("No category changes detected.")
                    else:
                        updated_count = update_bank_statement_categories(conn, updates)
                        st.success(f"Updated categories for {updated_count} saved bank statement rows.")
                        maybe_rerun()

        with st.expander("Delete Banking Data", expanded=False):
            if filtered_df.empty:
                st.info("No rows available to delete under the current filters.")
            else:
                select_all_filtered = st.checkbox(
                    "Select all filtered banking rows",
                    key="delete_bank_select_all"
                )

                deletable_view = filtered_df[["id", "txn_date", "bank_name", "description", "income_amount", "expense_amount", "currency", "category"]].copy()
                deletable_view.insert(0, "select_for_delete", bool(select_all_filtered))
                edited_delete_df = st.data_editor(
                    deletable_view,
                    key="delete_bank_rows_editor",
                    use_container_width=True,
                    hide_index=True,
                    disabled=["id", "txn_date", "bank_name", "description", "income_amount", "expense_amount", "currency", "category"],
                    column_config={
                        "select_for_delete": st.column_config.CheckboxColumn("Delete", help="Tick rows you want to delete"),
                        "id": st.column_config.NumberColumn("ID", format="%d"),
                        "txn_date": st.column_config.DateColumn("Date"),
                        "bank_name": st.column_config.TextColumn("Bank"),
                        "description": st.column_config.TextColumn("Description"),
                        "income_amount": st.column_config.NumberColumn("Income", format="%.2f"),
                        "expense_amount": st.column_config.NumberColumn("Expense", format="%.2f"),
                        "currency": st.column_config.TextColumn("Currency"),
                        "category": st.column_config.TextColumn("Category")
                    }
                )

                selected_row_ids = edited_delete_df.loc[
                    edited_delete_df["select_for_delete"], "id"
                ].astype(int).tolist()
                st.caption(f"Selected rows for deletion: {len(selected_row_ids)}")

                confirm_delete = st.checkbox(
                    "I understand this action permanently deletes selected banking rows",
                    key="confirm_delete_bank_rows"
                )

                if st.button("Delete Selected Banking Data", key="delete_selected_bank_rows"):
                    if not selected_row_ids:
                        st.warning("Select at least one banking row using the Delete checkboxes.")
                    elif not confirm_delete:
                        st.warning("Please confirm deletion before proceeding.")
                    else:
                        deleted_count = delete_bank_statement_rows(conn, selected_row_ids, user_id=user_id)
                        st.success(f"Deleted {deleted_count} banking row(s).")
                        maybe_rerun()

        selected_bank_set = set(selected_banks or [])
        result_bank_set = set(filtered_df["bank_name"].dropna().astype(str).str.strip().unique().tolist())
        missing_banks = sorted(selected_bank_set - result_bank_set)
        if missing_banks:
            st.warning(
                "No matching rows for selected bank(s) under current filters: "
                + ", ".join(missing_banks)
                + ". Try broadening Date/Category/Type/Search filters."
            )

        render_saved_bank_insights(filtered_df, display_currency, selected_banks=selected_banks)

# In-page Add/Edit/Delete management (shown on each relevant page)
page_to_entry_type = {
    "Income Tracking": "Income",
    "Expenses Tracking": "Expense",
    "Investments": "Investment",
    "Fixed Deposits": "Fixed Deposit",
    "Real Estate": "Real Estate",
    "Cash": "Cash",
}

entry_type = page_to_entry_type.get(selected_page)
if entry_type:
    st.markdown("---")
    st.subheader(f"Manage {entry_type}")
    action_mode = st.radio(
        "Choose action",
        ["Add New", "Edit or Delete Existing"],
        horizontal=True,
        key=f"crud_action_{entry_type}",
    )

    if action_mode == "Edit or Delete Existing":
        crud_configs = {
            "Income": {
                "table": "income",
                "fields": ["source", "amount", "currency", "date", "type"],
                "numeric": ["amount"],
                "date": ["date"],
                "select": {"currency": ["USD", "EUR", "INR"], "type": ["salary", "side", "passive", "revenue", "service"]},
            },
            "Expense": {
                "table": "expenses",
                "fields": ["category", "amount", "currency", "date"],
                "numeric": ["amount"],
                "date": ["date"],
                "select": {"currency": ["USD", "EUR", "INR"]},
            },
            "Investment": {
                "table": "investments",
                "fields": ["category", "name", "invested_amount", "current_value", "currency", "date_purchased"],
                "numeric": ["invested_amount", "current_value"],
                "date": ["date_purchased"],
                "select": {"currency": ["USD", "EUR", "INR"], "category": ["Stocks", "Mutual Funds", "Crypto", "Bonds", "Other"]},
            },
            "Fixed Deposit": {
                "table": "fixed_deposits",
                "fields": ["bank", "principal", "interest_rate", "maturity_date", "maturity_value", "currency"],
                "numeric": ["principal", "interest_rate", "maturity_value"],
                "date": ["maturity_date"],
                "select": {"currency": ["USD", "EUR", "INR"]},
            },
            "Real Estate": {
                "table": "real_estate",
                "fields": ["property_name", "purchase_price", "current_value", "rental_income", "currency"],
                "numeric": ["purchase_price", "current_value", "rental_income"],
                "date": [],
                "select": {"currency": ["USD", "EUR", "INR"]},
            },
            "Cash": {
                "table": "cash",
                "fields": ["amount", "currency", "date"],
                "numeric": ["amount"],
                "date": ["date"],
                "select": {"currency": ["USD", "EUR", "INR"]},
            },
        }

        cfg = crud_configs[entry_type]
        table_name = cfg["table"]
        fields = cfg["fields"]
        number_fields = set(cfg["numeric"])
        date_fields = set(cfg["date"])
        select_fields = cfg["select"]

        base_df = get_data(conn, table_name, account_type=account_type, user_id=user_id)
        if base_df.empty:
            st.info(f"No {entry_type.lower()} entries available.")
        else:
            editable_df = base_df[["id"] + fields].copy()
            for col in date_fields:
                if col in editable_df.columns:
                    editable_df[col] = pd.to_datetime(editable_df[col], errors="coerce").dt.date

            editable_df.insert(0, "select_for_delete", False)
            editable_df.insert(0, "select_for_edit", False)

            c1, c2 = st.columns(2)
            select_all_edit = c1.checkbox("Select All for Edit", key=f"select_all_edit_{entry_type}")
            select_all_delete = c2.checkbox("Select All for Delete", key=f"select_all_delete_{entry_type}")
            if select_all_edit:
                editable_df["select_for_edit"] = True
            if select_all_delete:
                editable_df["select_for_delete"] = True

            column_cfg = {
                "select_for_edit": st.column_config.CheckboxColumn("Edit", help="Tick rows to update"),
                "select_for_delete": st.column_config.CheckboxColumn("Delete", help="Tick rows to delete"),
                "id": st.column_config.NumberColumn("ID", disabled=True),
            }
            for field in fields:
                if field in select_fields:
                    column_cfg[field] = st.column_config.SelectboxColumn(field.replace("_", " ").title(), options=select_fields[field])
                elif field in number_fields:
                    column_cfg[field] = st.column_config.NumberColumn(field.replace("_", " ").title(), format="%.2f")
                elif field in date_fields:
                    column_cfg[field] = st.column_config.DateColumn(field.replace("_", " ").title())
                else:
                    column_cfg[field] = st.column_config.TextColumn(field.replace("_", " ").title())

            edited_grid = st.data_editor(
                editable_df,
                key=f"crud_grid_{entry_type}",
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                column_config=column_cfg,
                disabled=["id"],
            )

            # Read current selections from the grid
            _edit_rows_now = edited_grid.loc[edited_grid["select_for_edit"]]
            _delete_ids_now = edited_grid.loc[edited_grid["select_for_delete"], "id"].tolist()

            # Persist to session_state so a confirm-checkbox rerun can't lose them
            _edit_key = f"_sel_edit_{entry_type}"
            _del_key  = f"_sel_del_{entry_type}"
            if not _edit_rows_now.empty:
                st.session_state[_edit_key] = _edit_rows_now
            elif _edit_key not in st.session_state:
                st.session_state[_edit_key] = _edit_rows_now
            if _delete_ids_now:
                st.session_state[_del_key] = _delete_ids_now
            elif _del_key not in st.session_state:
                st.session_state[_del_key] = _delete_ids_now

            selected_edit_rows  = st.session_state[_edit_key]
            selected_delete_ids = st.session_state[_del_key]
            _pending_update_key = f"_pending_update_{entry_type}"
            _pending_update_retry_key = f"_pending_update_retry_{entry_type}"

            a1, a2 = st.columns(2)
            with a1:
                if st.button(f"Update Selected {entry_type}", key=f"update_selected_{entry_type}"):
                    # Use a pending flag to make update single-click reliable even when
                    # the data editor is still syncing the last in-cell edit.
                    st.session_state[_pending_update_key] = True
                    st.session_state[_pending_update_retry_key] = 0
                    maybe_rerun()

                if st.session_state.get(_pending_update_key, False):
                    if selected_edit_rows.empty:
                        retries = int(st.session_state.get(_pending_update_retry_key, 0))
                        if retries < 1:
                            # One extra rerun gives data_editor checkbox/cell edits time to sync.
                            st.session_state[_pending_update_retry_key] = retries + 1
                            maybe_rerun()
                        else:
                            st.session_state[_pending_update_key] = False
                            st.session_state[_pending_update_retry_key] = 0
                            st.warning("Select at least one row in the Edit column.")
                    else:
                        st.session_state[_pending_update_key] = False
                        st.session_state[_pending_update_retry_key] = 0
                        set_clause = ", ".join([f"{f}=?" for f in fields])
                        if user_id:
                            update_sql = f"UPDATE {table_name} SET {set_clause} WHERE id=? AND user_id=?"
                        else:
                            update_sql = f"UPDATE {table_name} SET {set_clause} WHERE id=?"
                        updated_count = 0
                        for _, row in selected_edit_rows.iterrows():
                            values = []
                            for f in fields:
                                val = row[f]
                                if f in date_fields and pd.notna(val):
                                    val = str(val)
                                values.append(val)
                            if user_id:
                                conn.execute(update_sql, tuple(values + [int(row["id"]), user_id]))
                            else:
                                conn.execute(update_sql, tuple(values + [int(row["id"])]))
                            updated_count += 1
                        conn.commit()
                        st.success(f"Updated {updated_count} row(s).")
                        st.session_state.pop(_edit_key, None)
                        maybe_rerun()

            with a2:
                confirm_delete = st.checkbox(
                    f"Confirm delete selected {entry_type.lower()} rows",
                    key=f"confirm_delete_{entry_type}",
                )
                if st.button(f"Delete Selected {entry_type}", key=f"delete_selected_{entry_type}"):
                    if not selected_delete_ids:
                        st.warning("Select at least one row in the Delete column.")
                    elif not confirm_delete:
                        st.warning("Please confirm deletion before proceeding.")
                    else:
                        placeholders = ",".join(["?"] * len(selected_delete_ids))
                        ids = tuple(int(v) for v in selected_delete_ids)
                        if user_id:
                            conn.execute(
                                f"DELETE FROM {table_name} WHERE id IN ({placeholders}) AND user_id = ?",
                                ids + (user_id,)
                            )
                        else:
                            conn.execute(f"DELETE FROM {table_name} WHERE id IN ({placeholders})", ids)
                        conn.commit()
                        st.success(f"Deleted {len(selected_delete_ids)} row(s).")
                        st.session_state.pop(_del_key, None)
                        maybe_rerun()

    else:
        if entry_type == "Income":
            with st.form("add_income"):
                source = st.text_input("Source")
                amount = st.number_input("Amount", min_value=0.0)
                currency = st.selectbox("Currency", ["USD", "EUR", "INR"])
                date = st.date_input("Date")
                inc_type = st.selectbox("Type", ["salary", "side", "passive", "revenue", "service"])
                submitted = st.form_submit_button("Add Income")
                if submitted:
                    conn.execute("INSERT INTO income (source, amount, currency, date, type, account_type, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (source, amount, currency, str(date), inc_type, account_type, st.session_state.user_id))
                    conn.commit()
                    st.success("Income added!")
                    maybe_rerun()

        elif entry_type == "Expense":
            with st.form("add_expense"):
                category = st.text_input("Category")
                amount = st.number_input("Amount", min_value=0.0)
                currency = st.selectbox("Currency", ["USD", "EUR", "INR"])
                date = st.date_input("Date")
                submitted = st.form_submit_button("Add Expense")
                if submitted:
                    conn.execute("INSERT INTO expenses (category, amount, currency, date, account_type, user_id) VALUES (?, ?, ?, ?, ?, ?)", (category, amount, currency, str(date), account_type, st.session_state.user_id))
                    conn.commit()
                    st.success("Expense added!")
                    maybe_rerun()

        elif entry_type == "Investment":
            with st.form("add_investment"):
                category = st.selectbox("Category", ["Stocks", "Mutual Funds", "Crypto", "Bonds", "Other"])
                name = st.text_input("Name/Description")
                invested_amount = st.number_input("Invested Amount", min_value=0.0)
                current_value = st.number_input("Current Value", min_value=0.0)
                currency = st.selectbox("Currency", ["USD", "EUR", "INR"])
                date_purchased = st.date_input("Date Purchased")
                submitted = st.form_submit_button("Add Investment")
                if submitted:
                    conn.execute("INSERT INTO investments (category, name, invested_amount, current_value, currency, date_purchased, account_type, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (category, name, invested_amount, current_value, currency, str(date_purchased), account_type, st.session_state.user_id))
                    conn.commit()
                    st.success("Investment added!")
                    maybe_rerun()

        elif entry_type == "Fixed Deposit":
            with st.form("add_fd"):
                bank = st.text_input("Bank Name")
                principal = st.number_input("Principal Amount", min_value=0.0)
                interest_rate = st.number_input("Interest Rate (%)", min_value=0.0, max_value=100.0)
                maturity_date = st.date_input("Maturity Date")
                maturity_value = st.number_input("Maturity Value", min_value=0.0)
                currency = st.selectbox("Currency", ["USD", "EUR", "INR"])
                submitted = st.form_submit_button("Add Fixed Deposit")
                if submitted:
                    conn.execute("INSERT INTO fixed_deposits (bank, principal, interest_rate, maturity_date, maturity_value, currency, account_type, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (bank, principal, interest_rate, str(maturity_date), maturity_value, currency, account_type, st.session_state.user_id))
                    conn.commit()
                    st.success("Fixed Deposit added!")
                    maybe_rerun()

        elif entry_type == "Real Estate":
            with st.form("add_re"):
                property_name = st.text_input("Property Name")
                purchase_price = st.number_input("Purchase Price", min_value=0.0)
                current_value = st.number_input("Current Market Value", min_value=0.0)
                rental_income = st.number_input("Monthly Rental Income", min_value=0.0)
                currency = st.selectbox("Currency", ["USD", "EUR", "INR"])
                submitted = st.form_submit_button("Add Real Estate")
                if submitted:
                    conn.execute("INSERT INTO real_estate (property_name, purchase_price, current_value, rental_income, currency, account_type, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (property_name, purchase_price, current_value, rental_income, currency, account_type, st.session_state.user_id))
                    conn.commit()
                    st.success("Real Estate added!")
                    maybe_rerun()

        elif entry_type == "Cash":
            with st.form("add_cash"):
                amount = st.number_input("Amount", min_value=0.0)
                currency = st.selectbox("Currency", ["USD", "EUR", "INR"])
                date = st.date_input("Date")
                submitted = st.form_submit_button("Add Cash")
                if submitted:
                    conn.execute("INSERT INTO cash (amount, currency, date, account_type, user_id) VALUES (?, ?, ?, ?, ?)", (amount, currency, str(date), account_type, st.session_state.user_id))
                    conn.commit()
                    st.success("Cash added!")
                    maybe_rerun()

if conn:
    conn.close()
