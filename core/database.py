import sqlite3
import json
import os

class DatabaseManager:
    def __init__(self, db_filename='ai_data.db'):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(os.path.dirname(script_dir), db_filename)
        self.create_tables()

    def _get_conn(self):
        """Helper to get SQLite connection with busy timeout to prevent database locks."""
        return sqlite3.connect(self.db_path, timeout=30.0)

    def create_tables(self):
        """Memastikan tabel snapshots selalu ada."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT,
                price REAL,
                high REAL,
                low REAL,
                features_json TEXT,
                label INTEGER,
                sell_label INTEGER
            )
        ''')
        
        # ponytail migration: lazily add columns to old databases
        for col in ['sell_label', 'high', 'low', 'model_version_hash']:
            try:
                cursor.execute(f"ALTER TABLE snapshots ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass # column already exists
        # ponytail: table to track live trades and link them to ML probabilities
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS live_trades (
                trade_id INTEGER PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                direction TEXT,
                entry_price REAL,
                exit_price REAL,
                profit REAL,
                trade_duration REAL,
                features_json TEXT,
                macro_bias TEXT,
                probability REAL,
                model_version_hash TEXT,
                status TEXT,
                outcome TEXT
            )
        ''')
        try:
            cursor.execute("ALTER TABLE live_trades ADD COLUMN model_version_hash TEXT")
        except sqlite3.OperationalError:
            pass
            
        conn.commit()
        conn.close()

    def save_snapshot(self, symbol, price, features, label=None, sell_label=None, high=None, low=None, model_version_hash=None):
        """Menyimpan fitur ke database."""
        conn = self._get_conn()
        cursor = conn.cursor()
        features_json = json.dumps(features)
        
        from datetime import datetime
        from zoneinfo import ZoneInfo
        wib_time = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M:%S")
        
        query = """
        INSERT INTO snapshots (timestamp, symbol, price, high, low, features_json, label, sell_label, model_version_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(query, (wib_time, symbol, price, high, low, features_json, label, sell_label, model_version_hash))
        conn.commit()
        conn.close()

    def log_trade_open(self, trade_id, direction, entry_price, features, macro_bias, probability, model_version_hash=None):
        """Ponytail: Log when a trade is sent to MT5 with model version hash"""
        conn = self._get_conn()
        cursor = conn.cursor()
        feat_str = json.dumps(features)
        
        from datetime import datetime
        from zoneinfo import ZoneInfo
        wib_time = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M:%S")
        
        query = """
        INSERT OR IGNORE INTO live_trades 
        (trade_id, timestamp, direction, entry_price, features_json, macro_bias, probability, model_version_hash, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
        """
        cursor.execute(query, (trade_id, wib_time, direction, entry_price, feat_str, macro_bias, probability, model_version_hash))
        conn.commit()
        conn.close()

    def log_trade_close(self, trade_id, exit_price, profit, duration):
        """Ponytail: Update trade when MT5 tells us it closed"""
        conn = self._get_conn()
        cursor = conn.cursor()
        outcome = "WIN" if profit > 0 else "LOSS"
        
        query = """
        UPDATE live_trades 
        SET exit_price = ?, profit = ?, trade_duration = ?, status = 'CLOSED', outcome = ?
        WHERE trade_id = ?
        """
        cursor.execute(query, (exit_price, profit, duration, outcome, trade_id))
        conn.commit()
        conn.close()