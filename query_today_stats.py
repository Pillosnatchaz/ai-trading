import sqlite3
import pandas as pd
from datetime import datetime

conn = sqlite3.connect('ai_data.db')
query = "SELECT * FROM live_trades WHERE timestamp >= date('now')"
df = pd.read_sql_query(query, conn)

if df.empty:
    print("No trades found for today.")
else:
    # Filter completed trades
    completed_trades = df.dropna(subset=['outcome', 'profit'])
    
    if completed_trades.empty:
        print("No completed trades found for today yet.")
    else:
        wins = len(completed_trades[completed_trades['outcome'] == 'WIN'])
        losses = len(completed_trades[completed_trades['outcome'] == 'LOSS'])
        total_profit = completed_trades['profit'].sum()
        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        
        print("\n--- TODAY'S LIVE PERFORMANCE ---")
        print(f"Total Completed Trades: {total_trades}")
        print(f"Wins: {wins}")
        print(f"Losses: {losses}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Total Profit/Loss: {total_profit:.2f}")

conn.close()
