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
    # Ambil semua data
    df = pd.read_sql_query("SELECT id, price, label, sell_label FROM snapshots ORDER BY id ASC", conn)

    if df.empty:
        print("[!] Tidak ada data di database.")
        conn.close()
        return

    # Inisialisasi labeler (misal: 20 pips SL, 40 pips TP, batas 60 candle)
    labeler = TripleBarrierLabeler(sl_pips=20, tp_pips=40, max_bars=60)
    # ponytail: secondary labeler to test 1:1.5 ratio theoretically
    labeler_15 = TripleBarrierLabeler(sl_pips=20, tp_pips=30, max_bars=60)
    
    prices = df['price'].values
    ids = df['id'].values
    current_labels = df['label'].values
    
    updates = []
    buy_stats = {1: 0, -1: 0, -2: 0, -3: 0, 0: 0}
    sell_stats = {1: 0, -1: 0, -2: 0, -3: 0, 0: 0}
    
    buy_stats_15 = {1: 0, -1: 0, -2: 0, -3: 0, 0: 0}
    sell_stats_15 = {1: 0, -1: 0, -2: 0, -3: 0, 0: 0}
    
    print(f"[*] Menganalisa {len(prices)} baris data untuk pelabelan...")

    for i in range(len(prices)):
        current_price = prices[i]
        future_prices = prices[i+1 : i+1+labeler.max_bars]

        if len(future_prices) == 0:
            continue

        buy_label = labeler.get_label(current_price, future_prices, direction='buy')
        sell_label = labeler.get_label(current_price, future_prices, direction='sell')
        
        buy_label_15 = labeler_15.get_label(current_price, future_prices, direction='buy')
        sell_label_15 = labeler_15.get_label(current_price, future_prices, direction='sell')
        
        buy_stats[buy_label] += 1
        sell_stats[sell_label] += 1
        
        buy_stats_15[buy_label_15] += 1
        sell_stats_15[sell_label_15] += 1
        
        if pd.isnull(current_labels[i]) or pd.isnull(df['sell_label'].values[i]):
            updates.append((buy_label, sell_label, int(ids[i])))
            
    print("\n[+] --- WR Prediction Verification ---")
    b_total = buy_stats[1] + buy_stats[-1] + buy_stats[-2] + buy_stats[-3]
    b_wr = (buy_stats[1] / b_total * 100) if b_total > 0 else 0
    print(f"BUY  (1:2) Win Rate: {b_wr:.2f}% (Wins: {buy_stats[1]}, Losses: {buy_stats[-1]}, Fast SOTW: {buy_stats[-2]}, Slow SOTW: {buy_stats[-3]}, Timeout: {buy_stats[0]})")
    
    s_total = sell_stats[1] + sell_stats[-1] + sell_stats[-2] + sell_stats[-3]
    s_wr = (sell_stats[1] / s_total * 100) if s_total > 0 else 0
    print(f"SELL (1:2) Win Rate: {s_wr:.2f}% (Wins: {sell_stats[1]}, Losses: {sell_stats[-1]}, Fast SOTW: {sell_stats[-2]}, Slow SOTW: {sell_stats[-3]}, Timeout: {sell_stats[0]})")
    print("--------------------------------------")
    
    print("\n[+] --- THEORETICAL 1:1.5 (20SL/30TP) ---")
    b_total_15 = buy_stats_15[1] + buy_stats_15[-1] + buy_stats_15[-2] + buy_stats_15[-3]
    b_wr_15 = (buy_stats_15[1] / b_total_15 * 100) if b_total_15 > 0 else 0
    print(f"BUY  (1:1.5) Win Rate: {b_wr_15:.2f}% (Wins: {buy_stats_15[1]}, Losses: {buy_stats_15[-1]}, Fast SOTW: {buy_stats_15[-2]}, Slow SOTW: {buy_stats_15[-3]}, Timeout: {buy_stats_15[0]})")
    
    s_total_15 = sell_stats_15[1] + sell_stats_15[-1] + sell_stats_15[-2] + sell_stats_15[-3]
    s_wr_15 = (sell_stats_15[1] / s_total_15 * 100) if s_total_15 > 0 else 0
    print(f"SELL (1:1.5) Win Rate: {s_wr_15:.2f}% (Wins: {sell_stats_15[1]}, Losses: {sell_stats_15[-1]}, Fast SOTW: {sell_stats_15[-2]}, Slow SOTW: {sell_stats_15[-3]}, Timeout: {sell_stats_15[0]})")
    print("--------------------------------------\n")

    if len(updates) > 0:
        cursor = conn.cursor()
        cursor.executemany("UPDATE snapshots SET label = ?, sell_label = ? WHERE id = ?", updates)
        conn.commit()
        print(f"[+] Berhasil mengupdate dan melabeli {len(updates)} baris data!")
    else:
        print("[*] Tidak ada data baru yang bisa dilabeli (mungkin data masa depan kurang).")

    conn.close()

if __name__ == "__main__":
    label_database()