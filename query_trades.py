import sqlite3
import pandas as pd

conn = sqlite3.connect('ai_data.db')
df = pd.read_sql_query("SELECT trade_id, timestamp, direction, entry_price, exit_price, profit, probability, outcome FROM live_trades ORDER BY timestamp DESC LIMIT 20", conn)
print(df.to_string())
