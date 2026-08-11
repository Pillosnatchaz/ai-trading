import sqlite3
import pandas as pd
import json
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

def run_experiment(direction='buy'):
    conn = sqlite3.connect('ai_data.db')
    target_col = 'label' if direction == 'buy' else 'sell_label'
    query = f"SELECT features_json, {target_col} FROM snapshots WHERE {target_col} IS NOT NULL"
    df_raw = pd.read_sql_query(query, conn)
    conn.close()

    data_list = []
    for idx, row in df_raw.iterrows():
        try:
            features = json.loads(row['features_json'])
            features['target_label'] = 1 if row[target_col] == 1 else 0
            data_list.append(features)
        except:
            continue
            
    df = pd.DataFrame(data_list)
    if 'time' in df.columns:
        df['hour'] = pd.to_datetime(df['time'], unit='s').dt.hour
        
    df = df.drop(columns=['is_near_ob', 'dist_to_bull_ob', 'dist_to_bear_ob', 'macro_bias', 'live_prob_buy', 'live_prob_sell', 'session', 'time'], errors='ignore')

    # --- MODEL 1: ALL 24 HOURS ---
    X = df.drop(columns=['target_label'])
    y = df['target_label']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    model_all = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, class_weight='balanced')
    model_all.fit(X_train, y_train)
    acc_all = accuracy_score(y_test, model_all.predict(X_test))
    
    # --- MODEL 2: ONLY LONDON & OVERLAP (7 to 15 UTC) ---
    df_filtered = df[df['hour'].isin([7,8,9,10,11,12,13,14,15])]
    X_f = df_filtered.drop(columns=['target_label'])
    y_f = df_filtered['target_label']
    
    X_train_f, X_test_f, y_train_f, y_test_f = train_test_split(X_f, y_f, test_size=0.2, random_state=42)
    model_f = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, class_weight='balanced')
    model_f.fit(X_train_f, y_train_f)
    acc_filtered = accuracy_score(y_test_f, model_f.predict(X_test_f))

    print(f"\n--- {direction.upper()} MODEL COMPARISON ---")
    print(f"1. 24-Hour Model (Trained on {len(df)} rows): {acc_all*100:.2f}% Accuracy")
    print(f"2. Filtered Model (Trained on {len(df_filtered)} rows): {acc_filtered*100:.2f}% Accuracy")

run_experiment('buy')
run_experiment('sell')
