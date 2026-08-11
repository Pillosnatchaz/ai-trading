import sqlite3
import pandas as pd
import json

conn = sqlite3.connect('ai_data.db')
query = "SELECT * FROM live_trades WHERE timestamp >= date('now')"
df = pd.read_sql_query(query, conn)

if df.empty:
    print("No trades found for today.")
else:
    # Filter completed trades
    completed_trades = df.dropna(subset=['outcome', 'profit']).copy()
    
    if completed_trades.empty:
        print("No completed trades found for today yet.")
    else:
        # Extract session from features_json if possible
        def get_sess(json_str):
            try:
                data = json.loads(json_str)
                return data.get('session', 'UNKNOWN')
            except:
                return 'UNKNOWN'
                
        completed_trades['session'] = completed_trades['features_json'].apply(get_sess)
        
        print("\n--- TODAY'S PERFORMANCE BY SESSION ---")
        
        # Group by session
        grouped = completed_trades.groupby('session')
        
        for name, group in grouped:
            wins = len(group[group['outcome'] == 'WIN'])
            losses = len(group[group['outcome'] == 'LOSS'])
            total_profit = group['profit'].sum()
            total_trades = wins + losses
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            
            print(f"\n[{name}]")
            print(f"  Trades: {total_trades}")
            print(f"  Wins: {wins} | Losses: {losses}")
            print(f"  Win Rate: {win_rate:.2f}%")
            print(f"  Profit/Loss: {total_profit:.2f}")

conn.close()
