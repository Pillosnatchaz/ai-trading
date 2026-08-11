"""
Replays MT4 historical CSV data through the exact live feature builder.
Saves to 'historical_snapshots' table so it doesn't pollute live data.
"""
import pandas as pd
import sqlite3
import json
import sys
from pathlib import Path
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent))
from data_engine.feature_builder import FeatureBuilder

DB_PATH = r"E:\Projects\ai-trading-iso\ai_data.db"
CSV_PATH = "history_dump.csv"

def init_historical_table():
    conn = sqlite3.connect(DB_PATH)
    # Exact same schema as snapshots, just different name
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historical_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            symbol TEXT,
            price REAL,
            features_json TEXT,
            label INTEGER,
            sell_label INTEGER,
            high REAL,
            low REAL,
            model_version_hash TEXT
        )
    """)
    # Add index for fast triple barrier labeling later
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_ts ON historical_snapshots(timestamp)")
    conn.close()

def build_history():
    if not Path(CSV_PATH).exists():
        print(f"[!] Please copy {CSV_PATH} from MT4 MQL4/Files/ to here first.")
        return

    print(f"[*] Loading {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    # Simulate bid/ask for spread (approx 3 points = 0.3 pips on gold, adjust if needed)
    df['bid'] = df['close']
    df['ask'] = df['close'] + 0.3

    print("[*] Resampling higher timeframes (M5, M15, H1, H4)...")
    df.set_index('timestamp', inplace=True)
    m5 = df['close'].resample('5min').last().reindex(df.index).ffill()
    m15 = df['close'].resample('15min').last().reindex(df.index).ffill()
    h1 = df['close'].resample('1h').last().reindex(df.index).ffill()
    h4 = df['close'].resample('4h').last().reindex(df.index).ffill()
    df.reset_index(inplace=True)

    df['m5_close'] = m5.values
    df['m15_close'] = m15.values
    df['h1_close'] = h1.values
    df['h4_close'] = h4.values

    builder = FeatureBuilder()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("[*] Replaying history through FeatureBuilder...")
    # Start at index 100 to give indicators (like EMA 50) time to warm up
    batch = []
    for i in tqdm(range(100, len(df))):
        # Pass a rolling window of 100 candles to the builder
        window = df.iloc[i-100:i+1]
        features = builder.build(window)
        
        row = window.iloc[-1]
        batch.append((
            str(row['timestamp']),
            "XAUUSD",
            row['close'],
            json.dumps(features),
            None, # label (calculated later)
            None, # sell_label (calculated later)
            row['high'],
            row['low'],
            "BACKTEST"
        ))

        # Batch insert for speed
        if len(batch) >= 1000:
            cursor.executemany("""
                INSERT INTO historical_snapshots 
                (timestamp, symbol, price, features_json, label, sell_label, high, low, model_version_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
            conn.commit()
            batch = []

    if batch:
        cursor.executemany("""
            INSERT INTO historical_snapshots 
            (timestamp, symbol, price, features_json, label, sell_label, high, low, model_version_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)
        conn.commit()
    
    conn.close()
    print("[+] Done! Data saved to 'historical_snapshots' table.")
    print("    Next step: run triple_barrier.py on the historical_snapshots table to generate labels.")

if __name__ == "__main__":
    init_historical_table()
    build_history()
