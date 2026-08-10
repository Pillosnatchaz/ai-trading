import sqlite3
import json
import pandas as pd

conn = sqlite3.connect('E:/Projects/ai-trading/ai_data.db')
print(conn.execute("PRAGMA table_info(live_trades)").fetchall())

try:
    df = pd.read_sql_query("SELECT * FROM live_trades ORDER BY id DESC LIMIT 15", conn)
    for idx, row in df.iterrows():
        f = json.loads(row['features_json']) if 'features_json' in row and row['features_json'] else {}
        sess = f.get('session', 'UNKNOWN')
        sl = row.get('sl_pips', 'N/A')
        tp = row.get('tp_pips', 'N/A')
        print(f"Trade {row.get('id')}: {sess} | {row.get('direction')} | SL: {sl} | TP: {tp}")
except Exception as e:
    print('Error:', e)
