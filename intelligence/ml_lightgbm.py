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
    def __init__(self, db_filename='ai_data.db', direction='buy'):
        """
        Inisialisasi ML Engine.
        direction: 'buy' atau 'sell'.
        """
        self.direction = direction
        model_filename = f'lgbm_model_{direction}.pkl'
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
        # Ambil hanya data yang sudah memiliki label
        target_col = 'label' if self.direction == 'buy' else 'sell_label'
        # ponytail: PRD v4.0 — filter out Fast SOTW (-2, noise stops) from training set
        query = f"SELECT features_json, {target_col}, timestamp FROM snapshots WHERE {target_col} IS NOT NULL AND {target_col} != -2"
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        if len(rows) == 0:
            print("[!] Belum ada data berlabel untuk di-training.")
            return None

        data_list = []
        for feat_str, label, ts in rows:
            try:
                features = json.loads(feat_str)
                # Ubah label menjadi Binary: 1 (Hit TP) = 1, -1 & 0 & -3 (Clean Loss/Timeout/Slow SOTW) = 0
                features['target_label'] = 1 if label == 1 else 0
                features['timestamp'] = ts
                data_list.append(features)
            except json.JSONDecodeError:
                continue
                
        df = pd.DataFrame(data_list)
        
        # Ekstrak Jam (Hour) dari timestamp untuk Regime Filtering
        if 'timestamp' in df.columns:
            df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
            
        # ponytail: encode macro_bias strings into numbers for LightGBM
        if 'macro_bias' in df.columns:
            df['macro_bias'] = df['macro_bias'].map({'BEARISH': -1, 'NEUTRAL': 0, 'BULLISH': 1}).fillna(0)
            
        # ponytail: drop swing features and audit columns
        df = df.drop(columns=['is_near_ob', 'dist_to_bull_ob', 'dist_to_bear_ob', 'live_prob_buy', 'live_prob_sell', 'session', 'timestamp', 'rel_h4', 'rel_d1_open', 'dist_to_fvg'], errors='ignore')
        return df

    def train(self):
        """Melatih model LightGBM dari data historis."""
        print("[*] Mengambil data training dari database...")
        df = self.fetch_training_data()
        
        if df is None or len(df) < 50:
            print("[!] Data tidak cukup untuk training. Minimal 50 baris berlabel.")
            return

        print(f"[*] Total data siap train: {len(df)} baris (excl. Fast SOTW noise).")
        
        # Pisahkan Fitur (X) dan Target (y)
        X = df.drop(columns=['target_label'])
        y = df['target_label']
        
        # Simpan nama fitur agar konsisten saat prediksi live
        self.feature_names = list(X.columns)

        # Split 80% Training, 20% Testing dengan Embargo Gap (120 baris) untuk mencegah boundary leakage
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx - 120], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx - 120], y.iloc[split_idx:]

        print("[*] Melatih model LightGBM (dengan scale_pos_weight = 1.9)...")
        # ponytail: read from config so we can tune from one place
        from core.config import LGBM_ESTIMATORS, LGBM_LEARNING_RATE, LGBM_MAX_DEPTH
        
        # Calculate pos_weight for class imbalance (~34% win minority)
        n_neg = (y_train == 0).sum()
        n_pos = (y_train == 1).sum()
        pos_weight = (n_neg / n_pos) if n_pos > 0 else 1.9
        
        self.model = lgb.LGBMClassifier(
            n_estimators=LGBM_ESTIMATORS,
            learning_rate=LGBM_LEARNING_RATE,
            max_depth=LGBM_MAX_DEPTH,
            scale_pos_weight=pos_weight,
            random_state=42,
        )
        
        self.model.fit(X_train, y_train)

        # Evaluasi
        y_pred = self.model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        # ponytail: show baseline so we don't fool ourselves with inflated accuracy
        baseline_acc = (y_test == 0).sum() / len(y_test)
        print(f"\n[+] Training Selesai!")
        print(f"    Baseline (always predict loss): {baseline_acc * 100:.2f}%")
        print(f"    Model Accuracy:                 {acc * 100:.2f}%  (lift: +{(acc - baseline_acc) * 100:.1f}%)")
        print(f"    Trades taken: {(y_pred == 1).sum()} / {len(y_pred)} ({(y_pred == 1).sum() / len(y_pred) * 100:.1f}%)")
        print("\nClassification Report:")
        print(classification_report(y_test, y_pred))
        
        # Simpan audit log ke DB
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('''CREATE TABLE IF NOT EXISTS ml_logs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                            direction TEXT,
                            accuracy REAL,
                            baseline REAL,
                            lift REAL,
                            trades_taken_pct REAL,
                            total_samples INTEGER
                        )''')
            conn.execute('''INSERT INTO ml_logs (direction, accuracy, baseline, lift, trades_taken_pct, total_samples)
                            VALUES (?, ?, ?, ?, ?, ?)''', 
                         (self.direction, acc * 100, baseline_acc * 100, (acc - baseline_acc) * 100, 
                          (y_pred == 1).sum() / len(y_pred) * 100, len(df)))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[!] Gagal menyimpan audit log ML: {e}")

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
        
        # ponytail: Use UTC to match SQLite CURRENT_TIMESTAMP used in training
        import datetime
        df_live['hour'] = datetime.datetime.utcnow().hour
        
        # ponytail: encode macro_bias string to number (same as training)
        if 'macro_bias' in df_live.columns:
            df_live['macro_bias'] = df_live['macro_bias'].map({'BEARISH': -1, 'NEUTRAL': 0, 'BULLISH': 1}).fillna(0)
        
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
                print(f"[*] Model AI (LightGBM - {self.direction.upper()}) berhasil dimuat.")
            except Exception as e:
                print(f"[!] Gagal memuat model: {e}")

# Fungsi eksekusi manual untuk training
if __name__ == "__main__":
    print("\n" + "="*30)
    print(" TRAINING BUY MODEL")
    print("="*30)
    predictor_buy = LightGBMPredictor(direction='buy')
    predictor_buy.train()
    
    print("\n" + "="*30)
    print(" TRAINING SELL MODEL")
    print("="*30)
    predictor_sell = LightGBMPredictor(direction='sell')
    predictor_sell.train()