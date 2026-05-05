import sqlite3

conn = sqlite3.connect('C:/PROJECT/FINANCE/finance-dashboard/finance.db')

# 1. Update admin user profile
conn.execute("UPDATE users SET first_name=?, last_name=? WHERE id=1", ('Niraj', 'Bajpai'))
row = conn.execute("SELECT id, username, first_name, last_name, role FROM users WHERE id=1").fetchone()
print("Updated user profile:", row)

# 2. Assign all NULL user_id rows to admin across every data table
tables = ['income', 'expenses', 'investments', 'fixed_deposits', 'real_estate', 'cash', 'bank_statements']
for t in tables:
    try:
        cur = conn.execute("UPDATE " + t + " SET user_id='admin' WHERE user_id IS NULL")
        print(t + ": " + str(cur.rowcount) + " rows updated")
    except Exception as e:
        print(t + ": ERROR - " + str(e))

conn.commit()
conn.close()
print("Done.")
