import sqlite3, pandas as pd, json
conn = sqlite3.connect('ai_data.db')
df = pd.read_sql_query("SELECT timestamp, features_json FROM snapshots WHERE timestamp >= date('now')", conn)

for idx, row in df.iterrows():
    if row['features_json']:
        feat = json.loads(row['features_json'])
        b = feat.get('live_prob_buy', 0)
        s = feat.get('live_prob_sell', 0)
        if b >= 0.57 or s >= 0.57:
            print(f"{row['timestamp']} | BUY: {b:.4f} | SELL: {s:.4f} | Session: {feat.get('session')}")
