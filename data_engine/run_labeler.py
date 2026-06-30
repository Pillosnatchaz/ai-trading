import sqlite3
import pandas as pd
import os
from .triple_barrier import TripleBarrierLabeler

def label_database(db_filename='ai_data.db'):
    """
    Membaca data historis dari database, menghitung Triple Barrier Label,
    dan mengupdate kolom 'label' yang masih NULL.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    db_path = os.path.join(root_dir, db_filename)

    if not os.path.exists(db_path):
        print(f"[!] Database tidak ditemukan: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    # Ambil semua data (kita butuh urutan harga untuk melihat ke masa depan)
    df = pd.read_sql_query("SELECT id, price, label FROM snapshots ORDER BY id ASC", conn)

    if df.empty:
        print("[!] Tidak ada data di database.")
        conn.close()
        return

    # Inisialisasi labeler (misal: 20 pips SL, 40 pips TP, batas 60 candle)
    labeler = TripleBarrierLabeler(sl_pips=20, tp_pips=40, max_bars=60)
    prices = df['price'].values
    ids = df['id'].values
    current_labels = df['label'].values
    
    updates = []
    buy_stats = {1: 0, -1: 0, 0: 0}
    sell_stats = {1: 0, -1: 0, 0: 0}
    
    print(f"[*] Menganalisa {len(prices)} baris data untuk pelabelan...")

    for i in range(len(prices)):
        current_price = prices[i]
        future_prices = prices[i+1 : i+1+labeler.max_bars]

        if len(future_prices) == 0:
            continue

        buy_label = labeler.get_label(current_price, future_prices, direction='buy')
        sell_label = labeler.get_label(current_price, future_prices, direction='sell')
        
        buy_stats[buy_label] += 1
        sell_stats[sell_label] += 1
        
        if pd.isnull(current_labels[i]):
            # ponytail: still saving buy_label to db to avoid schema changes (YAGNI)
            updates.append((buy_label, int(ids[i])))
            
    print("\n[+] --- WR Prediction Verification ---")
    b_total = buy_stats[1] + buy_stats[-1]
    b_wr = (buy_stats[1] / b_total * 100) if b_total > 0 else 0
    print(f"BUY  Win Rate: {b_wr:.2f}% (Wins: {buy_stats[1]}, Losses: {buy_stats[-1]}, Timeout: {buy_stats[0]})")
    
    s_total = sell_stats[1] + sell_stats[-1]
    s_wr = (sell_stats[1] / s_total * 100) if s_total > 0 else 0
    print(f"SELL Win Rate: {s_wr:.2f}% (Wins: {sell_stats[1]}, Losses: {sell_stats[-1]}, Timeout: {sell_stats[0]})")
    print("--------------------------------------\n")

    if len(updates) > 0:
        cursor = conn.cursor()
        cursor.executemany("UPDATE snapshots SET label = ? WHERE id = ?", updates)
        conn.commit()
        print(f"[+] Berhasil mengupdate dan melabeli {len(updates)} baris data!")
    else:
        print("[*] Tidak ada data baru yang bisa dilabeli (mungkin data masa depan kurang).")

    conn.close()

if __name__ == "__main__":
    label_database()