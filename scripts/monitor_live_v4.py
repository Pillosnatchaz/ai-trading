import sys
import os
sys.path.insert(0, r"G:\Projects\ai-trading")

import sqlite3
import json
import pandas as pd

def monitor_live_v4():
    conn = sqlite3.connect("ai_data.db")
    
    # 1. Total Snapshots & Recent Count
    total_snaps = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    v4_snaps = conn.execute("SELECT COUNT(*) FROM snapshots WHERE model_version_hash IS NOT NULL").fetchone()[0]
    
    # 2. Latest 5 Snapshots
    df_recent = pd.read_sql("""
        SELECT id, timestamp, price, features_json, model_version_hash 
        FROM snapshots 
        WHERE model_version_hash IS NOT NULL 
        ORDER BY id DESC LIMIT 5
    """, conn)
    
    # 3. Live Trades Summary
    df_trades = pd.read_sql("""
        SELECT trade_id, timestamp, direction, entry_price, probability, model_version_hash, status 
        FROM live_trades 
        ORDER BY trade_id DESC LIMIT 10
    """, conn)
    
    conn.close()
    
    print("\n==================================================")
    print("       MIA v4.0 LIVE MONITORING SCOREBOARD")
    print("==================================================")
    print(f" Total Database Snapshots: {total_snaps}")
    print(f" MIA v4.0 Logged Snapshots: {v4_snaps}")
    
    print("\n--- LATEST 5 LIVE M1 SNAPSHOTS ---")
    if not df_recent.empty:
        for idx, row in df_recent.iterrows():
            feat = json.loads(row['features_json'])
            p_buy = feat.get('live_prob_buy', 0) * 100
            p_sell = feat.get('live_prob_sell', 0) * 100
            sess = feat.get('session', 'N/A')
            rel_h1 = feat.get('rel_h1', 0)
            print(f"  ID: {row['id']} | Time: {row['timestamp']} | Session: {sess} | Price: {row['price']} | BUY: {p_buy:.1f}% | SELL: {p_sell:.1f}% | RelH1: {rel_h1:.4f} | Hash: {row['model_version_hash']}")
    else:
        print("  No v4 snapshots logged yet.")
        
    print("\n--- RECENT LIVE TRADES LOGGED ---")
    if not df_trades.empty:
        print(df_trades.to_string(index=False))
    else:
        print("  No live trades opened yet in this session.")
    print("==================================================\n")

if __name__ == "__main__":
    monitor_live_v4()
