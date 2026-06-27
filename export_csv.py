import sqlite3
import pandas as pd
import json

conn = sqlite3.connect('ai_data.db')
df = pd.read_sql_query("SELECT features_json, label FROM snapshots", conn)
df = pd.json_normalize(df['features_json'].apply(lambda x: json.loads(x) if x else {}))
df.to_csv('snapshots_export.csv', index=False)
print("[*] Exported cleanly to snapshots_export.csv")
