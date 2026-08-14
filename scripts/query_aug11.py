import sqlite3
import pandas as pd
import json

db_path = r'E:\Projects\ai-trading-iso\ai_data.db'
conn = sqlite3.connect(db_path)
df = pd.read_sql_query("SELECT * FROM live_trades WHERE timestamp LIKE '2026-08-11%'", conn)

if df.empty:
    print("No trades found for Aug 11.")
else:
    # Filter only closed trades (where profit is not null)
    df = df[df['profit'].notna()]
    if df.empty:
        print("No closed trades found for Aug 11.")
    else:
        def get_session(row):
            try:
                features = json.loads(row['features_json'])
                # main_loop saves current_session in features if it's not natively there?
                # Let's check wib hour from timestamp if session isn't saved
                # In feature_builder it isn't saved, but we can look at timestamp.
                # Assuming timestamp is WIB (UTC+7)
                hour = pd.to_datetime(row['timestamp']).hour
                if 5 <= hour < 14:
                    return 'ASIAN'
                elif 14 <= hour < 19:
                    return 'LONDON'
                elif 19 <= hour < 22:
                    return 'OVERLAP'
                elif 22 <= hour or hour < 5:
                    return 'LATE_NY'
                return 'UNKNOWN'
            except:
                return 'UNKNOWN'
                
        df['session'] = df.apply(get_session, axis=1)
        
        # Summary for whole day
        total_trades = len(df)
        wins = len(df[df['profit'] > 0])
        losses = len(df[df['profit'] < 0])
        wr = wins / total_trades * 100 if total_trades > 0 else 0
        total_pnl = df['profit'].sum()
        
        print(f"--- WHOLE DAY SUMMARY (Aug 11) ---")
        print(f"Trades: {total_trades}")
        print(f"Wins: {wins} | Losses: {losses}")
        print(f"Win Rate: {wr:.1f}%")
        print(f"Total PnL: ${total_pnl:.2f}\n")
        
        # Breakdown by session
        print(f"--- BREAKDOWN BY SESSION ---")
        for session in df['session'].unique():
            sdf = df[df['session'] == session]
            s_trades = len(sdf)
            s_wins = len(sdf[sdf['profit'] > 0])
            s_losses = len(sdf[sdf['profit'] < 0])
            s_wr = s_wins / s_trades * 100 if s_trades > 0 else 0
            s_pnl = sdf['profit'].sum()
            print(f"[{session}] Trades: {s_trades:2d} | W: {s_wins:2d} L: {s_losses:2d} | WR: {s_wr:5.1f}% | PnL: ${s_pnl:>7.2f}")

conn.close()
