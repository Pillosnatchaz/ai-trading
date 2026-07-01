import sqlite3
import json
import os

class DatabaseManager:
    def __init__(self, db_filename='ai_data.db'):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(os.path.dirname(script_dir), db_filename)
        self.create_tables()

    def create_tables(self):
        """Memastikan tabel snapshots selalu ada."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT,
                price REAL,
                features_json TEXT,
                label INTEGER,
                sell_label INTEGER
            )
        ''')
        
        # ponytail migration: lazily add sell_label to old databases
        try:
            cursor.execute("ALTER TABLE snapshots ADD COLUMN sell_label INTEGER")
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
                status TEXT,
                outcome TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def save_snapshot(self, symbol, price, features, label=None, sell_label=None):
        """Menyimpan fitur ke database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        features_json = json.dumps(features)
        
        query = """
        INSERT INTO snapshots (symbol, price, features_json, label, sell_label)
        VALUES (?, ?, ?, ?, ?)
        """
        cursor.execute(query, (symbol, price, features_json, label, sell_label))
        conn.commit()
        conn.close()

    def log_trade_open(self, trade_id, direction, entry_price, features, macro_bias, probability):
        """Ponytail: Log when a trade is sent to MT5"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        feat_str = json.dumps(features)
        
        query = """
        INSERT INTO live_trades 
        (trade_id, direction, entry_price, features_json, macro_bias, probability, status)
        VALUES (?, ?, ?, ?, ?, ?, 'OPEN')
        """
        cursor.execute(query, (trade_id, direction, entry_price, feat_str, macro_bias, probability))
        conn.commit()
        conn.close()

    def log_trade_close(self, trade_id, exit_price, profit, duration):
        """Ponytail: Update trade when MT5 tells us it closed"""
        conn = sqlite3.connect(self.db_path)
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