import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import create_connection, create_tables, create_users_table, insert_sample_data, insert_default_users, authenticate_user, get_data, calculate_net_worth, calculate_income_expenses
from datetime import datetime

# Page config
st.set_page_config(page_title="Personal Finance Dashboard", layout="wide", initial_sidebar_state="expanded")

# Exchange rates (base USD)
EXCHANGE_RATES = {
    'USD': 1.0,
    'EUR': 0.85,
    'INR': 83.0
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


def init_session_state():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""
        st.session_state.auth_error = ""


def logout():
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.auth_error = ""


def show_login_form(conn):
    st.title("Finance Dashboard Login")
    st.write("Enter your username and password to access the dashboard.")
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
                st.session_state.auth_error = ""
            else:
                st.session_state.auth_error = "Invalid username or password"
    if st.session_state.get("auth_error"):
        st.error(st.session_state.auth_error)

# Connect to database
conn = create_connection("finance.db")
if conn:
    create_tables(conn)
    create_users_table(conn)
    insert_default_users(conn)
    # Check if data exists, if not insert sample
    if pd.read_sql_query("SELECT COUNT(*) FROM income", conn).iloc[0, 0] == 0:
        insert_sample_data(conn)
else:
    st.error("Failed to connect to database")
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

st.sidebar.title("Filters & Controls")
st.sidebar.write(f"Logged in as **{st.session_state.username}**")
mode = st.sidebar.radio("Mode", ["Personal", "Business"])
account_type = mode.lower()
period = st.sidebar.selectbox("Time Period", ["Monthly", "Yearly", "All"], index=0)
category_filter = st.sidebar.selectbox("Category Filter", ["All", "Income", "Expenses", "Investments", "Fixed Deposits", "Real Estate"], index=0)
display_currency = st.sidebar.selectbox("Display Currency", ["USD", "EUR", "INR"], index=0)

# Main title
st.title("Personal Finance Dashboard")

# Tabs for sections
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs(["Overview", "Income Tracking", "Expenses Tracking", "Investments", "Fixed Deposits", "Real Estate", "Fund Allocation", "Insights", "Filters"])

with tab1:
    st.header(f"{mode} Overview")
    col1, col2, col3, col4 = st.columns(4)
    net_worth = calculate_net_worth(conn, account_type)
    income, expenses, savings_rate = calculate_income_expenses(conn, period.lower(), account_type)
    
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

with tab2:
    st.header(f"{mode} Income Tracking")
    income_df = get_data(conn, "income", account_type=account_type)
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

with tab3:
    st.header(f"{mode} Expenses Tracking")
    expenses_df = get_data(conn, "expenses", account_type=account_type)
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

with tab4:
    st.header(f"{mode} Investments")
    inv_df = get_data(conn, "investments", account_type=account_type)
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

with tab5:
    st.header(f"{mode} Fixed Deposits")
    fd_df = get_data(conn, "fixed_deposits", account_type=account_type)
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

with tab6:
    st.header(f"{mode} Real Estate")
    re_df = get_data(conn, "real_estate", account_type=account_type)
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

with tab7:
    st.header(f"{mode} Fund Allocation")
    # Calculate allocations
    inv_df = get_data(conn, "investments", account_type=account_type)
    fd_df = get_data(conn, "fixed_deposits", account_type=account_type)
    re_df = get_data(conn, "real_estate", account_type=account_type)
    cash_df = get_data(conn, "cash", account_type=account_type)
    income_df = get_data(conn, "income", account_type=account_type)
    expenses_df = get_data(conn, "expenses", account_type=account_type)
    
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

with tab8:
    st.header(f"{mode} Insights & Analytics")
    # Simple insights
    income, expenses, savings_rate = calculate_income_expenses(conn, 'monthly', account_type)
    if savings_rate < 20:
        st.warning("Savings rate is below 20%. Consider reducing expenses or increasing income.")
    else:
        st.success("Good savings rate!")
    
    # Trends
    income_df = get_data(conn, "income", account_type=account_type)
    expenses_df = get_data(conn, "expenses", account_type=account_type)
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

with tab9:
    st.header(f"{mode} Filters & Data View")
    
    # Apply filters
    if category_filter == "All":
        # Show all data
        st.subheader("All Financial Data")
        all_data = []
        
        income_df = get_data(conn, "income", account_type=account_type)
        if not income_df.empty:
            income_df['type'] = 'Income'
            income_df['amount_display'] = income_df.apply(lambda x: convert_currency(x['amount'], x['currency'], display_currency), axis=1)
            income_df['amount_display'] = income_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            all_data.append(income_df[['date', 'type', 'source', 'amount_display', 'currency']])
        
        expenses_df = get_data(conn, "expenses", account_type=account_type)
        if not expenses_df.empty:
            expenses_df['type'] = 'Expense'
            expenses_df['amount_display'] = expenses_df.apply(lambda x: convert_currency(x['amount'], x['currency'], display_currency), axis=1)
            expenses_df['amount_display'] = expenses_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            all_data.append(expenses_df[['date', 'type', 'category', 'amount_display', 'currency']])
        
        investments_df = get_data(conn, "investments", account_type=account_type)
        if not investments_df.empty:
            investments_df['type'] = 'Investment'
            investments_df['amount_display'] = investments_df.apply(lambda x: convert_currency(x['current_value'], x['currency'], display_currency), axis=1)
            investments_df['amount_display'] = investments_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            all_data.append(investments_df[['date_purchased', 'type', 'name', 'amount_display', 'currency']])
        
        fd_df = get_data(conn, "fixed_deposits", account_type=account_type)
        if not fd_df.empty:
            fd_df['type'] = 'Fixed Deposit'
            fd_df['amount_display'] = fd_df.apply(lambda x: convert_currency(x['maturity_value'], x['currency'], display_currency), axis=1)
            fd_df['amount_display'] = fd_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            all_data.append(fd_df[['maturity_date', 'type', 'bank', 'amount_display', 'currency']])
        
        re_df = get_data(conn, "real_estate", account_type=account_type)
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
        income_df = get_data(conn, "income", account_type=account_type)
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
        expenses_df = get_data(conn, "expenses", account_type=account_type)
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
        inv_df = get_data(conn, "investments", account_type=account_type)
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
        fd_df = get_data(conn, "fixed_deposits", account_type=account_type)
        if not fd_df.empty:
            fd_df['amount_display'] = fd_df.apply(lambda x: convert_currency(x['maturity_value'], x['currency'], display_currency), axis=1)
            fd_df['amount_display'] = fd_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            st.dataframe(fd_df[['maturity_date', 'bank', 'amount_display', 'currency']])
        else:
            st.write("No fixed deposits data available")
    
    elif category_filter == "Real Estate":
        st.subheader("Real Estate Data")
        re_df = get_data(conn, "real_estate", account_type=account_type)
        if not re_df.empty:
            re_df['amount_display'] = re_df.apply(lambda x: convert_currency(x['current_value'], x['currency'], display_currency), axis=1)
            re_df['amount_display'] = re_df.apply(lambda x: format_currency(x['amount_display'], display_currency), axis=1)
            st.dataframe(re_df[['property_name', 'purchase_price', 'amount_display', 'currency']])
        else:
            st.write("No real estate data available")

# Add/Edit section in sidebar
st.sidebar.header("Add/Edit Entries")
edit_mode = st.sidebar.checkbox("Edit Mode")
entry_type = st.sidebar.selectbox("Entry Type", ["Income", "Expense", "Investment", "Fixed Deposit", "Real Estate", "Cash"])

if edit_mode:
    # Edit existing entries
    if entry_type == "Income":
        st.sidebar.subheader("Edit Income")
        income_df = get_data(conn, "income", account_type=account_type)
        if not income_df.empty:
            income_options = [f"{row['id']}: {row['source']} - {format_currency(row['amount'], row['currency'])}" for _, row in income_df.iterrows()]
            selected_income = st.sidebar.selectbox("Select Income to Edit", income_options)
            if selected_income:
                income_id = int(selected_income.split(':')[0])
                income_row = income_df[income_df['id'] == income_id].iloc[0]
                
                with st.sidebar.form("edit_income"):
                    source = st.text_input("Source", value=income_row['source'])
                    amount = st.number_input("Amount", min_value=0.0, value=float(income_row['amount']))
                    currency = st.selectbox("Currency", ["USD", "EUR", "INR"], index=["USD", "EUR", "INR"].index(income_row['currency']))
                    date = st.date_input("Date", value=pd.to_datetime(income_row['date']).date())
                    inc_type = st.selectbox("Type", ["salary", "side", "passive", "revenue", "service"], index=["salary", "side", "passive", "revenue", "service"].index(income_row['type']))
                    col1, col2 = st.columns(2)
                    with col1:
                        submitted = st.form_submit_button("Update Income")
                    with col2:
                        delete_submitted = st.form_submit_button("Delete Income", type="secondary")
                    if submitted:
                        conn.execute("UPDATE income SET source=?, amount=?, currency=?, date=?, type=? WHERE id=?", (source, amount, currency, str(date), inc_type, income_id))
                        conn.commit()
                        st.success("Income updated!")
                        st.rerun()
                    if delete_submitted:
                        conn.execute("DELETE FROM income WHERE id=?", (income_id,))
                        conn.commit()
                        st.success("Income deleted!")
                        st.rerun()
        else:
            st.sidebar.write("No income entries to edit")
    
    elif entry_type == "Expense":
        st.sidebar.subheader("Edit Expense")
        expenses_df = get_data(conn, "expenses", account_type=account_type)
        if not expenses_df.empty:
            expense_options = [f"{row['id']}: {row['category']} - {format_currency(row['amount'], row['currency'])}" for _, row in expenses_df.iterrows()]
            selected_expense = st.sidebar.selectbox("Select Expense to Edit", expense_options)
            if selected_expense:
                expense_id = int(selected_expense.split(':')[0])
                expense_row = expenses_df[expenses_df['id'] == expense_id].iloc[0]
                
                with st.sidebar.form("edit_expense"):
                    category = st.text_input("Category", value=expense_row['category'])
                    amount = st.number_input("Amount", min_value=0.0, value=float(expense_row['amount']))
                    currency = st.selectbox("Currency", ["USD", "EUR", "INR"], index=["USD", "EUR", "INR"].index(expense_row['currency']))
                    date = st.date_input("Date", value=pd.to_datetime(expense_row['date']).date())
                    col1, col2 = st.columns(2)
                    with col1:
                        submitted = st.form_submit_button("Update Expense")
                    with col2:
                        delete_submitted = st.form_submit_button("Delete Expense", type="secondary")
                    if submitted:
                        conn.execute("UPDATE expenses SET category=?, amount=?, currency=?, date=? WHERE id=?", (category, amount, currency, str(date), expense_id))
                        conn.commit()
                        st.success("Expense updated!")
                        st.rerun()
                    if delete_submitted:
                        conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
                        conn.commit()
                        st.success("Expense deleted!")
                        st.rerun()
        else:
            st.sidebar.write("No expense entries to edit")
    
    elif entry_type == "Investment":
        st.sidebar.subheader("Edit Investment")
        inv_df = get_data(conn, "investments", account_type=account_type)
        if not inv_df.empty:
            inv_options = [f"{row['id']}: {row['name']} - {format_currency(row['current_value'], row['currency'])}" for _, row in inv_df.iterrows()]
            selected_inv = st.sidebar.selectbox("Select Investment to Edit", inv_options)
            if selected_inv:
                inv_id = int(selected_inv.split(':')[0])
                inv_row = inv_df[inv_df['id'] == inv_id].iloc[0]
                
                with st.sidebar.form("edit_investment"):
                    category = st.selectbox("Category", ["Stocks", "Mutual Funds", "Crypto", "Bonds", "Other"], index=["Stocks", "Mutual Funds", "Crypto", "Bonds", "Other"].index(inv_row['category']))
                    name = st.text_input("Name/Description", value=inv_row['name'])
                    invested_amount = st.number_input("Invested Amount", min_value=0.0, value=float(inv_row['invested_amount']))
                    current_value = st.number_input("Current Value", min_value=0.0, value=float(inv_row['current_value']))
                    currency = st.selectbox("Currency", ["USD", "EUR", "INR"], index=["USD", "EUR", "INR"].index(inv_row['currency']))
                    date_purchased = st.date_input("Date Purchased", value=pd.to_datetime(inv_row['date_purchased']).date())
                    col1, col2 = st.columns(2)
                    with col1:
                        submitted = st.form_submit_button("Update Investment")
                    with col2:
                        delete_submitted = st.form_submit_button("Delete Investment", type="secondary")
                    if submitted:
                        conn.execute("UPDATE investments SET category=?, name=?, invested_amount=?, current_value=?, currency=?, date_purchased=? WHERE id=?", (category, name, invested_amount, current_value, currency, str(date_purchased), inv_id))
                        conn.commit()
                        st.success("Investment updated!")
                        st.rerun()
                    if delete_submitted:
                        conn.execute("DELETE FROM investments WHERE id=?", (inv_id,))
                        conn.commit()
                        st.success("Investment deleted!")
                        st.rerun()
        else:
            st.sidebar.write("No investment entries to edit")
    
    elif entry_type == "Fixed Deposit":
        st.sidebar.subheader("Edit Fixed Deposit")
        fd_df = get_data(conn, "fixed_deposits", account_type=account_type)
        if not fd_df.empty:
            fd_options = [f"{row['id']}: {row['bank']} - {format_currency(row['maturity_value'], row['currency'])}" for _, row in fd_df.iterrows()]
            selected_fd = st.sidebar.selectbox("Select Fixed Deposit to Edit", fd_options)
            if selected_fd:
                fd_id = int(selected_fd.split(':')[0])
                fd_row = fd_df[fd_df['id'] == fd_id].iloc[0]
                
                with st.sidebar.form("edit_fd"):
                    bank = st.text_input("Bank Name", value=fd_row['bank'])
                    principal = st.number_input("Principal Amount", min_value=0.0, value=float(fd_row['principal']))
                    interest_rate = st.number_input("Interest Rate (%)", min_value=0.0, max_value=100.0, value=float(fd_row['interest_rate']))
                    maturity_date = st.date_input("Maturity Date", value=pd.to_datetime(fd_row['maturity_date']).date())
                    maturity_value = st.number_input("Maturity Value", min_value=0.0, value=float(fd_row['maturity_value']))
                    currency = st.selectbox("Currency", ["USD", "EUR", "INR"], index=["USD", "EUR", "INR"].index(fd_row['currency']))
                    col1, col2 = st.columns(2)
                    with col1:
                        submitted = st.form_submit_button("Update Fixed Deposit")
                    with col2:
                        delete_submitted = st.form_submit_button("Delete Fixed Deposit", type="secondary")
                    if submitted:
                        conn.execute("UPDATE fixed_deposits SET bank=?, principal=?, interest_rate=?, maturity_date=?, maturity_value=?, currency=? WHERE id=?", (bank, principal, interest_rate, str(maturity_date), maturity_value, currency, fd_id))
                        conn.commit()
                        st.success("Fixed Deposit updated!")
                        st.rerun()
                    if delete_submitted:
                        conn.execute("DELETE FROM fixed_deposits WHERE id=?", (fd_id,))
                        conn.commit()
                        st.success("Fixed Deposit deleted!")
                        st.rerun()
        else:
            st.sidebar.write("No fixed deposit entries to edit")
    
    elif entry_type == "Real Estate":
        st.sidebar.subheader("Edit Real Estate")
        re_df = get_data(conn, "real_estate", account_type=account_type)
        if not re_df.empty:
            re_options = [f"{row['id']}: {row['property_name']} - {format_currency(row['current_value'], row['currency'])}" for _, row in re_df.iterrows()]
            selected_re = st.sidebar.selectbox("Select Real Estate to Edit", re_options)
            if selected_re:
                re_id = int(selected_re.split(':')[0])
                re_row = re_df[re_df['id'] == re_id].iloc[0]
                
                with st.sidebar.form("edit_re"):
                    property_name = st.text_input("Property Name", value=re_row['property_name'])
                    purchase_price = st.number_input("Purchase Price", min_value=0.0, value=float(re_row['purchase_price']))
                    current_value = st.number_input("Current Market Value", min_value=0.0, value=float(re_row['current_value']))
                    rental_income = st.number_input("Monthly Rental Income", min_value=0.0, value=float(re_row['rental_income']))
                    currency = st.selectbox("Currency", ["USD", "EUR", "INR"], index=["USD", "EUR", "INR"].index(re_row['currency']))
                    col1, col2 = st.columns(2)
                    with col1:
                        submitted = st.form_submit_button("Update Real Estate")
                    with col2:
                        delete_submitted = st.form_submit_button("Delete Real Estate", type="secondary")
                    if submitted:
                        conn.execute("UPDATE real_estate SET property_name=?, purchase_price=?, current_value=?, rental_income=?, currency=? WHERE id=?", (property_name, purchase_price, current_value, rental_income, currency, re_id))
                        conn.commit()
                        st.success("Real Estate updated!")
                        st.rerun()
                    if delete_submitted:
                        conn.execute("DELETE FROM real_estate WHERE id=?", (re_id,))
                        conn.commit()
                        st.success("Real Estate deleted!")
                        st.rerun()
        else:
            st.sidebar.write("No real estate entries to edit")
    
    elif entry_type == "Cash":
        st.sidebar.subheader("Edit Cash")
        cash_df = get_data(conn, "cash", account_type=account_type)
        if not cash_df.empty:
            cash_options = [f"{row['id']}: {format_currency(row['amount'], row['currency'])} - {row['date']}" for _, row in cash_df.iterrows()]
            selected_cash = st.sidebar.selectbox("Select Cash to Edit", cash_options)
            if selected_cash:
                cash_id = int(selected_cash.split(':')[0])
                cash_row = cash_df[cash_df['id'] == cash_id].iloc[0]
                
                with st.sidebar.form("edit_cash"):
                    amount = st.number_input("Amount", min_value=0.0, value=float(cash_row['amount']))
                    currency = st.selectbox("Currency", ["USD", "EUR", "INR"], index=["USD", "EUR", "INR"].index(cash_row['currency']))
                    date = st.date_input("Date", value=pd.to_datetime(cash_row['date']).date())
                    col1, col2 = st.columns(2)
                    with col1:
                        submitted = st.form_submit_button("Update Cash")
                    with col2:
                        delete_submitted = st.form_submit_button("Delete Cash", type="secondary")
                    if submitted:
                        conn.execute("UPDATE cash SET amount=?, currency=?, date=? WHERE id=?", (amount, currency, str(date), cash_id))
                        conn.commit()
                        st.success("Cash updated!")
                        st.rerun()
                    if delete_submitted:
                        conn.execute("DELETE FROM cash WHERE id=?", (cash_id,))
                        conn.commit()
                        st.success("Cash deleted!")
                        st.rerun()
        else:
            st.sidebar.write("No cash entries to edit")

else:
    # Add new entries
    if entry_type == "Income":
        with st.sidebar.form("add_income"):
            source = st.text_input("Source")
            amount = st.number_input("Amount", min_value=0.0)
            currency = st.selectbox("Currency", ["USD", "EUR", "INR"])
            date = st.date_input("Date")
            inc_type = st.selectbox("Type", ["salary", "side", "passive", "revenue", "service"])
            submitted = st.form_submit_button("Add Income")
            if submitted:
                conn.execute("INSERT INTO income (source, amount, currency, date, type, account_type) VALUES (?, ?, ?, ?, ?, ?)", (source, amount, currency, str(date), inc_type, account_type))
                conn.commit()
                st.success("Income added!")
                st.rerun()
    elif entry_type == "Expense":
        with st.sidebar.form("add_expense"):
            category = st.text_input("Category")
            amount = st.number_input("Amount", min_value=0.0)
            currency = st.selectbox("Currency", ["USD", "EUR", "INR"])
            date = st.date_input("Date")
            submitted = st.form_submit_button("Add Expense")
            if submitted:
                conn.execute("INSERT INTO expenses (category, amount, currency, date, account_type) VALUES (?, ?, ?, ?, ?)", (category, amount, currency, str(date), account_type))
                conn.commit()
                st.success("Expense added!")
                st.rerun()
    elif entry_type == "Investment":
        with st.sidebar.form("add_investment"):
            category = st.selectbox("Category", ["Stocks", "Mutual Funds", "Crypto", "Bonds", "Other"])
            name = st.text_input("Name/Description")
            invested_amount = st.number_input("Invested Amount", min_value=0.0)
            current_value = st.number_input("Current Value", min_value=0.0)
            currency = st.selectbox("Currency", ["USD", "EUR", "INR"])
            date_purchased = st.date_input("Date Purchased")
            submitted = st.form_submit_button("Add Investment")
            if submitted:
                conn.execute("INSERT INTO investments (category, name, invested_amount, current_value, currency, date_purchased, account_type) VALUES (?, ?, ?, ?, ?, ?, ?)", (category, name, invested_amount, current_value, currency, str(date_purchased), account_type))
                conn.commit()
                st.success("Investment added!")
                st.rerun()
    elif entry_type == "Fixed Deposit":
        with st.sidebar.form("add_fd"):
            bank = st.text_input("Bank Name")
            principal = st.number_input("Principal Amount", min_value=0.0)
            interest_rate = st.number_input("Interest Rate (%)", min_value=0.0, max_value=100.0)
            maturity_date = st.date_input("Maturity Date")
            maturity_value = st.number_input("Maturity Value", min_value=0.0)
            currency = st.selectbox("Currency", ["USD", "EUR", "INR"])
            submitted = st.form_submit_button("Add Fixed Deposit")
            if submitted:
                conn.execute("INSERT INTO fixed_deposits (bank, principal, interest_rate, maturity_date, maturity_value, currency, account_type) VALUES (?, ?, ?, ?, ?, ?, ?)", (bank, principal, interest_rate, str(maturity_date), maturity_value, currency, account_type))
                conn.commit()
                st.success("Fixed Deposit added!")
                st.rerun()
    elif entry_type == "Real Estate":
        with st.sidebar.form("add_re"):
            property_name = st.text_input("Property Name")
            purchase_price = st.number_input("Purchase Price", min_value=0.0)
            current_value = st.number_input("Current Market Value", min_value=0.0)
            rental_income = st.number_input("Monthly Rental Income", min_value=0.0)
            currency = st.selectbox("Currency", ["USD", "EUR", "INR"])
            submitted = st.form_submit_button("Add Real Estate")
            if submitted:
                conn.execute("INSERT INTO real_estate (property_name, purchase_price, current_value, rental_income, currency, account_type) VALUES (?, ?, ?, ?, ?, ?)", (property_name, purchase_price, current_value, rental_income, currency, account_type))
                conn.commit()
                st.success("Real Estate added!")
                st.rerun()
    elif entry_type == "Cash":
        with st.sidebar.form("add_cash"):
            amount = st.number_input("Amount", min_value=0.0)
            currency = st.selectbox("Currency", ["USD", "EUR", "INR"])
            date = st.date_input("Date")
            submitted = st.form_submit_button("Add Cash")
            if submitted:
                conn.execute("INSERT INTO cash (amount, currency, date, account_type) VALUES (?, ?, ?, ?)", (amount, currency, str(date), account_type))
                conn.commit()
                st.success("Cash added!")
                st.rerun()

# Add similar for others, but for brevity, only two examples
# Similarly for others, but for brevity, only one example

if conn:
    conn.close()