# Personal & Business Finance Dashboard

A modern, interactive finance dashboard for both personal and business use, built with Streamlit, Python, and SQLite.

## Features

- **Dual Mode**: Switch between Personal and Business finance tracking.
- **Multi-Currency Support**: Add data in USD, EUR, or INR with proper formatting.
- **Overview**: Net worth, income vs expenses, savings rate with KPI tiles.
- **Income Tracking**: Track multiple sources with trends, charts, and detailed data tables.
- **Expenses Tracking**: Track spending categories with trends, charts, and detailed data tables.
- **Investments**: Portfolio allocation, profit/loss, performance charts with detailed data tables.
- **Fixed Deposits**: Maturity tracking and allocations.
- **Real Estate**: Property values, ROI, rental income.
- **Fund Allocation**: Visual allocation across categories.
- **Insights**: Trends and simple recommendations.
- **Filters**: Time and category filters.
- **Add/Edit/Delete**: Forms to add, edit, and delete financial entries for selected mode with currency selection.
- **Real-time Updates**: Changes are immediately visible after any CRUD operation.

## Edit Functionality

To edit existing entries:
1. Check the "Edit Mode" checkbox in the sidebar
2. Select the entry type you want to edit
3. Choose the specific entry from the dropdown list
4. Modify the fields as needed
5. Click the "Update" button to save changes
6. **Delete entries**: Click the red "Delete" button to remove entries

All entry types support editing and deleting: Income, Expenses, Investments, Fixed Deposits, Real Estate, and Cash.

**Real-time Updates**: All changes (add, edit, delete) are immediately reflected in the dashboard without needing to refresh the page.

## Installation

1. Clone or download the project.
2. Install dependencies: `pip install -r requirements.txt`
3. Run the app: `streamlit run app.py`

## Database

Uses SQLite (`finance.db`) with tables for income, expenses, investments, fixed_deposits, real_estate, cash.

Each table has an `account_type` column ('personal' or 'business') and a `currency` column ('USD', 'EUR', 'INR').

Sample data is inserted on first run for both modes.

## Usage

- Select mode (Personal or Business) in the sidebar.
- Navigate through tabs for different sections.
- Use sidebar filters to adjust views.
- Add new entries via sidebar forms (entries are added to the selected mode with selected currency).
- **Edit existing entries**: Toggle "Edit Mode" in the sidebar to select and modify existing entries.
- Amounts are displayed with appropriate currency symbols (€, $, ₹).

## Login

The app now requires login before the dashboard is visible. Default credentials are:

- `admin` / `admin123`
- `personal` / `personal123`
- `business` / `business123`

## Technologies

- Streamlit for UI
- Plotly for charts
- Pandas for data manipulation
- SQLite for database