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
    
    print(f"[*] Menganalisa {len(prices)} baris data untuk pelabelan...")

    for i in range(len(prices)):
        # Hanya labeli yang masih kosong (NaN / NULL)
        if pd.notnull(current_labels[i]):
            continue
            
        current_price = prices[i]
        # Ambil harga-harga yang terjadi SETELAH snapshot ini
        future_prices = prices[i+1 : i+1+labeler.max_bars]

        # Jika kita berada di ujung data dan belum cukup max_bars, kita skip dulu
        if len(future_prices) == 0:
            continue

        # Asumsikan kita melatih model untuk mendeteksi setup BUY
        # (Anda bisa menyesuaikan jika ingin mengevaluasi sell)
        label = labeler.get_label(current_price, future_prices, direction='buy')
        
        # Simpan tuple untuk update: (label_baru, id_baris)
        updates.append((label, int(ids[i])))

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