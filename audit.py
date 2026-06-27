import sqlite3
import pandas as pd
import json

def audit_449_snapshot():
    # Koneksi ke database baru
    conn = sqlite3.connect('ai_data.db')
    
    # Membaca data dari tabel 'snapshots'
    # Menggunakan kolom yang benar: 'features_json'
    try:
        query = "SELECT features_json, label FROM snapshots"
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f"[!] Error membaca database: {e}")
        return
    
    # Parse JSON features menjadi DataFrame
    # Menggunakan json.loads untuk mengubah string JSON menjadi dict
    features_df = pd.json_normalize(df['features_json'].apply(json.loads))
    
    # Gabungkan label kembali ke dataframe fitur
    features_df['label'] = df['label']
    
    # Analisis Korelasi (Pearson)
    # Kita melihat fitur mana yang memiliki hubungan terkuat dengan hasil trading (label)
    correlation = features_df.corrwith(features_df['label']).sort_values(ascending=False)
    
    print("[*] AUDIT 449 SNAPSHOT (DB BARU)")
    print("---------------------------------")
    print(f"Total baris data: {len(df)}")
    print("\n[+] Korelasi Fitur terhadap Label (Keberhasilan):")
    print(correlation.drop('label'))
    
    # Deteksi fitur yang berpotensi menjadi 'Noise' (korelasi mendekati 0)
    print("\n[+] Catatan:")
    for feature, corr in correlation.drop('label').items():
        if abs(corr) < 0.05:
            print(f" - Fitur '{feature}' tampaknya kurang informatif (corr: {corr:.4f})")
    
    conn.close()

if __name__ == "__main__":
    audit_449_snapshot()