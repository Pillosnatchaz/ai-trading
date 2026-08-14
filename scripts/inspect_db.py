import sqlite3
import pandas as pd

def inspect_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables in database:")
    for table in tables:
        table_name = table[0]
        print(f"\n--- Table: {table_name} ---")
        df = pd.read_sql_query(f"PRAGMA table_info('{table_name}')", conn)
        print(df[['name', 'type']])
        
        # Get count
        count = cursor.execute(f"SELECT COUNT(*) FROM '{table_name}'").fetchone()[0]
        print(f"Total rows: {count}")

        # Show a few sample rows
        if count > 0:
            sample = pd.read_sql_query(f"SELECT * FROM '{table_name}' LIMIT 3", conn)
            print("Sample data:")
            print(sample)
    conn.close()

if __name__ == "__main__":
    inspect_db("E:/Projects/ai-trading-iso/ai_data.db")
