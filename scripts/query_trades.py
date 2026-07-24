import sqlite3
import pandas as pd

conn = sqlite3.connect('ai_data.db')
df = pd.read_sql_query("SELECT * FROM live_trades ORDER BY trade_id DESC LIMIT 20", conn)

if df.empty:
    print("No trades found.")
else:
    print("\n--- LAST 20 LIVE TRADES ---")
    print(df[['trade_id', 'timestamp', 'direction', 'profit', 'outcome']].to_string())
    
    wins = len(df[df['outcome'] == 'WIN'])
    losses = len(df[df['outcome'] == 'LOSS'])
    total = wins + losses
    if total > 0:
        print(f"\nRecent Win Rate: {(wins/total)*100:.2f}% (Wins: {wins}, Losses: {losses})")
