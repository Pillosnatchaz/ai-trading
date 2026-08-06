import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import sqlite3
import json
import lightgbm as lgb
import joblib
from sklearn.metrics import accuracy_score, classification_report
from scipy.optimize import minimize

class MonotonicPlattScaler:
    """Platt Calibrator with strict non-negative slope constraint (coef >= 0).
    Guarantees calibrator NEVER inverts model ranking order under noise."""
    def __init__(self):
        self.coef_ = 1.0
        self.intercept_ = 0.0
        
    def fit(self, X_raw, y):
        X_flat = np.asarray(X_raw).flatten()
        y_flat = np.asarray(y).flatten()
        def loss(params):
            a, b = params
            z = a * X_flat + b
            p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
            eps = 1e-15
            p = np.clip(p, eps, 1 - eps)
            return -np.mean(y_flat * np.log(p) + (1 - y_flat) * np.log(1 - p))
        
        res = minimize(loss, [1.0, 0.0], bounds=[(0.0, None), (None, None)], method='L-BFGS-B')
        self.coef_ = float(res.x[0])
        self.intercept_ = float(res.x[1])
        
    def predict_proba(self, X_raw):
        X_flat = np.asarray(X_raw).flatten()
        z = self.coef_ * X_flat + self.intercept_
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        return np.column_stack([1 - p, p])

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

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        # Ambil hanya data yang sudah memiliki label
        target_col = 'label' if self.direction == 'buy' else 'sell_label'
        # ponytail: deduplicate snapshots by minute to ensure 1 clean row per M1 candle close and prevent data leakage
        query = f"""
        SELECT features_json, {target_col}, timestamp 
        FROM (
            SELECT features_json, {target_col}, timestamp, id,
                   ROW_NUMBER() OVER (PARTITION BY strftime('%Y-%m-%d %H:%M', timestamp) ORDER BY id DESC) as rn
            FROM snapshots
            WHERE {target_col} IS NOT NULL AND {target_col} != -2 AND timestamp >= '2026-07-24'
        ) WHERE rn = 1 ORDER BY id ASC
        """
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
            df['hour_utc'] = pd.to_datetime(df['timestamp']).dt.hour
            # ponytail: tag session per row for per-session calibrator fitting
            df['_wib_hour'] = (df['hour_utc'] + 7) % 24
            df['_session'] = 'OTHER'
            df.loc[(df['_wib_hour'] >= 14) & (df['_wib_hour'] < 19.5), '_session'] = 'LONDON'
            df.loc[(df['_wib_hour'] >= 19.5) & (df['_wib_hour'] <= 22), '_session'] = 'OVERLAP'
            df.loc[(df['_wib_hour'] >= 8) & (df['_wib_hour'] < 12), '_session'] = 'ASIAN'
            
        # ponytail: encode macro_bias & volatility_regime strings into numbers for LightGBM
        if 'macro_bias' in df.columns:
            df['macro_bias'] = df['macro_bias'].map({'BEARISH': -1, 'NEUTRAL': 0, 'BULLISH': 1}).fillna(0)
        if 'volatility_regime' in df.columns:
            df['volatility_regime'] = df['volatility_regime'].map({'LOW': 0, 'NORMAL': 1, 'HIGH': 2}).fillna(1)
            
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

        # Split 80% Training, 20% Testing dengan Embargo Gap (120 baris) untuk mencegah boundary leakage
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx - 120], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx - 120], y.iloc[split_idx:]

        # Split training set into sub-train (80%) and calibration (20%)
        cal_split = int(len(X_train) * 0.8)
        X_tr, X_cal = X_train.iloc[:cal_split], X_train.iloc[cal_split:]
        y_tr, y_cal = y_train.iloc[:cal_split], y_train.iloc[cal_split:]
        # ponytail: keep session tags for per-session calibrator fitting, then drop from features
        cal_sessions = df.iloc[X_cal.index]['_session'] if '_session' in df.columns else pd.Series(['OTHER'] * len(X_cal))

        print("[*] Melatih model LightGBM & Global True Logit Platt Calibrator (PRD §7)...")
        # ponytail: read from config so we can tune from one place
        from core.config import LGBM_ESTIMATORS, LGBM_LEARNING_RATE, LGBM_MAX_DEPTH
        from sklearn.linear_model import LogisticRegression

        # ponytail: drop internal session columns before training
        internal_cols = ['_wib_hour', '_session', 'hour_utc']
        X_tr = X_tr.drop(columns=[c for c in internal_cols if c in X_tr.columns], errors='ignore')
        X_cal = X_cal.drop(columns=[c for c in internal_cols if c in X_cal.columns], errors='ignore')
        X_test = X_test.drop(columns=[c for c in internal_cols if c in X_test.columns], errors='ignore')
        
        # Simpan nama fitur AFTER dropping internal cols so count matches model
        self.feature_names = list(X_tr.columns)
        
        # Calculate pos_weight for class imbalance (~34% win minority)
        n_neg = (y_tr == 0).sum()
        n_pos = (y_tr == 1).sum()
        pos_weight = (n_neg / n_pos) if n_pos > 0 else 1.9
        
        self.model = lgb.LGBMClassifier(
            n_estimators=LGBM_ESTIMATORS,
            learning_rate=LGBM_LEARNING_RATE,
            max_depth=LGBM_MAX_DEPTH,
            scale_pos_weight=pos_weight,
            random_state=42,
            verbose=-1
        )
        
        self.model.fit(X_tr, y_tr)

        # Fit Global True Logit Platt Calibration Layer
        raw_cal_probs = np.clip(self.model.predict_proba(X_cal)[:, 1], 1e-7, 1 - 1e-7)
        f_cal = np.log(raw_cal_probs / (1.0 - raw_cal_probs))
        
        self.calibrator = MonotonicPlattScaler()
        self.calibrator.fit(f_cal, y_cal)
        
        # ponytail: Disable Per-Session Calibrators. The dataset is too small, 
        # causing small-N variance to jack up the intercept and blindly output 80% win probs.
        self.session_calibrators = {}

        # Evaluasi dengan Global True Platt Calibrated probabilities
        raw_test_probs = np.clip(self.model.predict_proba(X_test)[:, 1], 1e-7, 1 - 1e-7)
        f_test = np.log(raw_test_probs / (1.0 - raw_test_probs))
        calib_test_probs = self.calibrator.predict_proba(f_test.reshape(-1, 1))[:, 1]
        y_pred = (calib_test_probs >= 0.45).astype(int)
        
        acc = accuracy_score(y_test, y_pred)
        baseline_acc = (y_test == 0).sum() / len(y_test)
        print(f"\n[+] Training & Global Platt Calibration Selesai!")
        print(f"    Baseline (always predict loss): {baseline_acc * 100:.2f}%")
        print(f"    Model Accuracy:                 {acc * 100:.2f}%  (lift: +{(acc - baseline_acc) * 100:.1f}%)")
        print(f"    Trades taken (prob >= 0.45):    {(y_pred == 1).sum()} / {len(y_pred)} ({(y_pred == 1).sum() / len(y_pred) * 100:.1f}%)")
        print("\nClassification Report:")
        print(classification_report(y_test, y_pred))
        
        # Simpan audit log ke DB
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
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

    def predict(self, features_dict, session=None, return_raw=False):
        """
        Melakukan prediksi dari 1 baris data live.
        Return: float probabilitas TRUE PLATT CALIBRATED (0.0 sampai 1.0) peluang keberhasilan trade.
        """
        if self.model is None or self.feature_names is None:
            return 0.0

        df_live = pd.DataFrame([features_dict])
        
        import datetime
        df_live['hour'] = datetime.datetime.utcnow().hour
        
        if 'macro_bias' in df_live.columns:
            df_live['macro_bias'] = df_live['macro_bias'].map({'BEARISH': -1, 'NEUTRAL': 0, 'BULLISH': 1}).fillna(0)
        if 'volatility_regime' in df_live.columns:
            df_live['volatility_regime'] = df_live['volatility_regime'].map({'LOW': 0, 'NORMAL': 1, 'HIGH': 2}).fillna(1)
        
        for col in self.feature_names:
            if col not in df_live.columns:
                df_live[col] = np.nan
                
        df_live = df_live[self.feature_names].astype(float)

        # Ambil raw probabilitas dari LightGBM
        raw_prob = float(self.model.predict_proba(df_live)[0][1])
        raw_prob_clipped = float(np.clip(raw_prob, 1e-7, 1.0 - 1e-7))
        
        # Convert to raw margin logit f = ln(p / (1 - p))
        f_live = float(np.log(raw_prob_clipped / (1.0 - raw_prob_clipped)))
        
        calibrated_prob = raw_prob
        # ponytail: Route through per-session calibrator if it exists
        if session and hasattr(self, 'session_calibrators') and session in self.session_calibrators:
            calibrated_prob = float(self.session_calibrators[session].predict_proba([[f_live]])[0][1])
        # Fallback to global calibrator
        elif hasattr(self, 'calibrator') and self.calibrator is not None:
            calibrated_prob = float(self.calibrator.predict_proba([[f_live]])[0][1])
            
        if return_raw:
            return calibrated_prob, raw_prob
        return calibrated_prob

    def save_model(self):
        """Menyimpan model ke disk."""
        model_data = {
            'model': self.model,
            'calibrator': getattr(self, 'calibrator', None),
            'session_calibrators': getattr(self, 'session_calibrators', {}),
            'feature_names': self.feature_names
        }
        joblib.dump(model_data, self.model_path)
        print(f"[*] Model berhasil disimpan di {self.model_path}")

    def get_model_version_hash(self):
        """PRD v4.0: Returns MD5 hash of the saved .pkl model artifact for live traceability."""
        import hashlib
        if os.path.exists(self.model_path):
            with open(self.model_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()[:10]
        return "UNINITIALIZED"

    def load_model(self):
        """Memuat model dari disk jika tersedia."""
        if os.path.exists(self.model_path):
            try:
                model_data = joblib.load(self.model_path)
                self.model = model_data['model']
                self.calibrator = model_data.get('calibrator', None)
                self.session_calibrators = model_data.get('session_calibrators', {})
                self.feature_names = model_data['feature_names']
                sess_count = len(self.session_calibrators)
                print(f"[*] Model AI (LightGBM + Isotonic Calibrated - {self.direction.upper()} | Hash: {self.get_model_version_hash()} | Session Calibrators: {sess_count}) berhasil dimuat.")
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