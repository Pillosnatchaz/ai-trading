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
                label INTEGER
            )
        ''')
        conn.commit()
        conn.close()

    def save_snapshot(self, symbol, price, features, label=None):
        """Menyimpan fitur ke database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        features_json = json.dumps(features)
        
        query = """
        INSERT INTO snapshots (symbol, price, features_json, label)
        VALUES (?, ?, ?, ?)
        """
        cursor.execute(query, (symbol, price, features_json, label))
        conn.commit()
        conn.close()