import sys
import os
import pandas as pd
import numpy as np
import sqlite3
import json
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression

# Adjust path to import local modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def fetch_v4_data(direction='buy'):
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ai_data.db')
    conn = sqlite3.connect(db_path)
    target_col = 'label' if direction == 'buy' else 'sell_label'
    
    # Only fetch data >= July 24
    query = f"""
    SELECT features_json, {target_col}, timestamp 
    FROM (
        SELECT features_json, {target_col}, timestamp, id,
               ROW_NUMBER() OVER (PARTITION BY strftime('%Y-%m-%d %H:%M', timestamp) ORDER BY id DESC) as rn
        FROM snapshots
        WHERE {target_col} IS NOT NULL AND {target_col} != -2 
          AND timestamp >= '2026-07-24'
    ) WHERE rn = 1 ORDER BY id ASC
    """
    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    if len(rows) == 0:
        return None

    data_list = []
    for feat_str, label, ts in rows:
        try:
            features = json.loads(feat_str)
            features['target_label'] = 1 if label == 1 else 0
            features['timestamp'] = ts
            data_list.append(features)
        except json.JSONDecodeError:
            continue
            
    df = pd.DataFrame(data_list)
    
    # Replicate ML engine preprocessing
    if 'timestamp' in df.columns:
        df['hour_utc'] = pd.to_datetime(df['timestamp']).dt.hour
        df['_wib_hour'] = (df['hour_utc'] + 7) % 24
        df['_session'] = 'OTHER'
        df.loc[(df['_wib_hour'] >= 14) & (df['_wib_hour'] < 19.5), '_session'] = 'LONDON'
        df.loc[(df['_wib_hour'] >= 19.5) & (df['_wib_hour'] <= 22), '_session'] = 'OVERLAP'
        df.loc[(df['_wib_hour'] >= 8) & (df['_wib_hour'] < 12), '_session'] = 'ASIAN'

    if 'macro_bias' in df.columns:
        df['macro_bias'] = df['macro_bias'].map({'BEARISH': -1, 'NEUTRAL': 0, 'BULLISH': 1}).fillna(0)
    if 'volatility_regime' in df.columns:
        df['volatility_regime'] = df['volatility_regime'].map({'LOW': 0, 'NORMAL': 1, 'HIGH': 2}).fillna(1)
        
    df = df.drop(columns=['is_near_ob', 'dist_to_bull_ob', 'dist_to_bear_ob', 'live_prob_buy', 'live_prob_sell', 'session', 'timestamp', 'rel_h4', 'rel_d1_open', 'dist_to_fvg'], errors='ignore')
    
    return df

def run_sweep(direction='buy'):
    print(f"\n{'='*50}")
    print(f" SWEEPING {direction.upper()} MODEL (v4 DATA ONLY >= 2026-07-24)")
    print(f"{'='*50}")
    
    df = fetch_v4_data(direction)
    if df is None or len(df) < 50: 
        print(f"Not enough data for {direction} (Rows: {len(df) if df is not None else 0}).")
        return
    
    print(f"Total Rows >= July 24: {len(df)}")
    
    X = df.drop(columns=['target_label'])
    y = df['target_label']
    
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx - 120], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx - 120], y.iloc[split_idx:]
    
    cal_split = int(len(X_train) * 0.8)
    X_tr, X_cal = X_train.iloc[:cal_split], X_train.iloc[cal_split:]
    y_tr, y_cal = y_train.iloc[:cal_split], y_train.iloc[cal_split:]
    
    internal_cols = ['_wib_hour', '_session', 'hour_utc']
    X_tr = X_tr.drop(columns=[c for c in internal_cols if c in X_tr.columns], errors='ignore')
    X_cal = X_cal.drop(columns=[c for c in internal_cols if c in X_cal.columns], errors='ignore')
    X_test = X_test.drop(columns=[c for c in internal_cols if c in X_test.columns], errors='ignore')
    
    import lightgbm as lgb
    from core.config import LGBM_ESTIMATORS, LGBM_LEARNING_RATE, LGBM_MAX_DEPTH
    
    n_neg = (y_tr == 0).sum()
    n_pos = (y_tr == 1).sum()
    pos_weight = (n_neg / n_pos) if n_pos > 0 else 1.9
    
    model = lgb.LGBMClassifier(
        n_estimators=LGBM_ESTIMATORS, 
        learning_rate=LGBM_LEARNING_RATE, 
        max_depth=LGBM_MAX_DEPTH, 
        scale_pos_weight=pos_weight, 
        random_state=42, 
        verbose=-1
    )
    model.fit(X_tr, y_tr)
    
    # Generate Raw Probabilities
    raw_cal = np.clip(model.predict_proba(X_cal)[:, 1], 1e-7, 1 - 1e-7)
    raw_test = np.clip(model.predict_proba(X_test)[:, 1], 1e-7, 1 - 1e-7)
    
    # Fit Platt (LogisticRegression on Logits)
    f_cal = np.log(raw_cal / (1.0 - raw_cal))
    f_test = np.log(raw_test / (1.0 - raw_test))
    platt = LogisticRegression(C=1.0, solver='lbfgs')
    platt.fit(f_cal.reshape(-1, 1), y_cal)
    platt_test = platt.predict_proba(f_test.reshape(-1, 1))[:, 1]
    
    # Fit Isotonic
    iso = IsotonicRegression(out_of_bounds='clip')
    iso.fit(raw_cal, y_cal)
    iso_test = iso.predict(raw_test)
    
    # 1. Plot Distribution
    bins = [0.0, 0.2, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.8, 1.0]
    print("\n[ Distribution of Probabilities (Test Set) ]")
    print(f"{'Bin':<15} | {'Raw Count':<10} | {'Platt Count':<12} | {'Iso Count':<10}")
    print("-" * 55)
    for i in range(len(bins)-1):
        b1, b2 = bins[i], bins[i+1]
        c_raw = sum((raw_test >= b1) & (raw_test < b2))
        c_platt = sum((platt_test >= b1) & (platt_test < b2))
        c_iso = sum((iso_test >= b1) & (iso_test < b2))
        print(f"{b1:.2f} - {b2:.2f}     | {c_raw:<10} | {c_platt:<12} | {c_iso:<10}")
        
    # 2. Sweep Thresholds
    print("\n[ Threshold Sweep (Test Set) ]")
    thresholds = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
    print(f"{'Thresh':<8} | {'Platt Trades':<12} | {'Platt WR%':<10} | {'Iso Trades':<12} | {'Iso WR%':<10}")
    print("-" * 62)
    for t in thresholds:
        p_trades = sum(platt_test >= t)
        p_wins = sum((platt_test >= t) & (y_test == 1))
        p_wr = (p_wins/p_trades*100) if p_trades > 0 else 0
        
        i_trades = sum(iso_test >= t)
        i_wins = sum((iso_test >= t) & (y_test == 1))
        i_wr = (i_wins/i_trades*100) if i_trades > 0 else 0
        
        print(f"{t:<8.2f} | {p_trades:<12} | {p_wr:<10.1f} | {i_trades:<12} | {i_wr:<10.1f}")

if __name__ == "__main__":
    run_sweep('buy')
    run_sweep('sell')
