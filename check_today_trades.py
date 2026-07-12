import sqlite3, pandas as pd, json

conn = sqlite3.connect('ai_data.db')
df = pd.read_sql_query("SELECT timestamp, direction, entry_price, profit, features_json FROM live_trades WHERE timestamp >= date('now')", conn)

print(f"{'Time':<20} | {'Dir':<4} | {'Price':<8} | {'Profit':<6} | {'rel_h1'}")
print("-" * 65)

for _, row in df.iterrows():
    rel_h1 = "N/A"
    if row['features_json']:
        feat = json.loads(row['features_json'])
        rel_h1 = feat.get('rel_h1', 'N/A')
        if isinstance(rel_h1, float):
            rel_h1 = f"{rel_h1:.5f}"
            
    profit = f"{row['profit']:.2f}" if pd.notnull(row['profit']) else "OPEN"
    print(f"{row['timestamp']:<20} | {row['direction']:<4} | {row['entry_price']:<8.2f} | {profit:<6} | {rel_h1}")

conn.close()
