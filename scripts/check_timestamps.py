import sqlite3, pandas as pd
conn = sqlite3.connect('ai_data.db')
df = pd.read_sql_query("SELECT timestamp FROM snapshots WHERE timestamp >= date('now') ORDER BY id DESC LIMIT 5", conn)
print(df)
