import sqlite3, pandas as pd

conn = sqlite3.connect('ai_data.db')
df = pd.read_sql_query("SELECT timestamp, profit, trade_duration FROM live_trades WHERE timestamp >= date('now') AND outcome IS NOT NULL AND profit > 0", conn)

df['hour'] = pd.to_datetime(df['timestamp']).dt.hour

print('=== WIN DURATION BY HOUR (WIB) ===')
for hour in sorted(df['hour'].unique()):
    subset = df[df['hour'] == hour]
    print(f'  Hour {hour:02d}:00 | Wins: {len(subset)} | Avg Duration: {subset["trade_duration"].mean():.0f}s ({subset["trade_duration"].mean()/60:.1f}min)')

conn.close()
