import sqlite3, pandas as pd
conn = sqlite3.connect('ai_data.db')
df = pd.read_sql_query("SELECT timestamp, direction, entry_price FROM live_trades WHERE timestamp >= '2026-07-09'", conn)
print("Trades today:")
print(df)
