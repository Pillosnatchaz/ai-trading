import pandas as pd
import numpy as np
import sqlite3
import json
import os
import lightgbm as lgb
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

class LightGBMPredictor:
    def __init__(self, db_filename='ai_data.db', model_filename='lgbm_model.pkl'):
        """
        Inisialisasi ML Engine.
        Secara otomatis mencari database dan file model yang tersimpan di root proyek.
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(script_dir)
        
        self.db_path = os.path.join(root_dir, db_filename)
        self.model_path = os.path.join(root_dir, 'intelligence', model_filename)
        
        self.model = None
        self.feature_names = None
        
        # Load model jika sudah ada
        self.load_model()

    def fetch_training_data(self):
        """Mengambil data dari SQLite, memecah JSON menjadi kolom DataFrame."""
        if not os.path.exists(self.db_path):
            print(f"[!] Database tidak ditemukan di {self.db_path}")
            return None

        conn = sqlite3.connect(self.db_path)
        # Ambil hanya data yang sudah memiliki label (selesai di-Triple Barrier)
        query = "SELECT features_json, label FROM snapshots WHERE label IS NOT NULL"
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        if len(rows) == 0:
            print("[!] Belum ada data berlabel untuk di-training.")
            return None

        data_list = []
        for feat_str, label in rows:
            try:
                features = json.loads(feat_str)
                # Ubah label menjadi Binary: 1 (Hit TP) = 1, selain itu (Hit SL/Timeout) = 0
                features['target_label'] = 1 if label == 1 else 0
                data_list.append(features)
            except json.JSONDecodeError:
                continue
                
        df = pd.DataFrame(data_list)
        df = df.drop(columns=['is_near_ob', 'dist_to_bull_ob', 'dist_to_bear_ob'], errors='ignore')
        return df

    def train(self):
        """Melatih model LightGBM dari data historis."""
        print("[*] Mengambil data training dari database...")
        df = self.fetch_training_data()
        
        if df is None or len(df) < 50:
            print("[!] Data tidak cukup untuk training. Minimal 50 baris berlabel.")
            return

        print(f"[*] Total data siap train: {len(df)} baris.")
        
        # Pisahkan Fitur (X) dan Target (y)
        X = df.drop(columns=['target_label'])
        y = df['target_label']
        
        # Simpan nama fitur agar konsisten saat prediksi live
        self.feature_names = list(X.columns)

        # Split 80% Training, 20% Testing
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        print("[*] Melatih model LightGBM...")
        self.model = lgb.LGBMClassifier(
            n_estimators=100,
            learning_rate=0.05,
            max_depth=5,
            random_state=42,
            class_weight='balanced' # Menangani data imbalanced jika Hit SL lebih banyak dari Hit TP
        )
        
        self.model.fit(X_train, y_train)

        # Evaluasi
        y_pred = self.model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        print(f"\n[+] Training Selesai! Accuracy di Test Set: {acc * 100:.2f}%")
        print("Classification Report:")
        print(classification_report(y_test, y_pred))

        # Simpan Model & Nama Fitur
        self.save_model()

    def predict(self, features_dict):
        """
        Melakukan prediksi dari 1 baris data live.
        Return: float probabilitas (0.0 sampai 1.0) peluang keberhasilan trade.
        """
        if self.model is None or self.feature_names is None:
            # print("[!] Model belum dilatih. Mengembalikan probabilitas 0.")
            return 0.0

        # Ubah single dict menjadi DataFrame 1 baris
        df_live = pd.DataFrame([features_dict])
        
        # Pastikan urutan dan jumlah kolom SAMA PERSIS dengan saat training
        # Jika ada fitur baru di live yang tidak ada saat training, buang.
        # Jika ada fitur kurang, isi dengan NaN (LightGBM bisa handle NaN)
        for col in self.feature_names:
            if col not in df_live.columns:
                df_live[col] = np.nan
                
        df_live = df_live[self.feature_names]

        # Ambil probabilitas untuk kelas 1 (Trade Sukses)
        probability = self.model.predict_proba(df_live)[0][1]
        return probability

    def save_model(self):
        """Menyimpan model ke disk."""
        model_data = {
            'model': self.model,
            'feature_names': self.feature_names
        }
        joblib.dump(model_data, self.model_path)
        print(f"[*] Model berhasil disimpan di {self.model_path}")

    def load_model(self):
        """Memuat model dari disk jika tersedia."""
        if os.path.exists(self.model_path):
            try:
                model_data = joblib.load(self.model_path)
                self.model = model_data['model']
                self.feature_names = model_data['feature_names']
                print("[*] Model AI (LightGBM) berhasil dimuat dan siap digunakan.")
            except Exception as e:
                print(f"[!] Gagal memuat model: {e}")

# Fungsi eksekusi manual untuk training
if __name__ == "__main__":
    predictor = LightGBMPredictor()
    predictor.train()