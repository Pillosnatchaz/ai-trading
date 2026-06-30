import sqlite3
import pandas as pd
import json
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=UserWarning)

from intelligence.ml_lightgbm import LightGBMPredictor

# ponytail: silence lightgbm loading spam
print("[*] Loading new model...")
import sys, os
old_stdout = sys.stdout
sys.stdout = open(os.devnull, 'w')
ml_model = LightGBMPredictor()
sys.stdout = old_stdout

conn = sqlite3.connect('ai_data.db')
df = pd.read_sql_query("SELECT features_json, label FROM snapshots WHERE label IS NOT NULL", conn)

old_wins, old_total = 0, 0
new_wins, new_total = 0, 0

print("[*] Evaluating rows...")
for _, row in df.iterrows():
    if not row['features_json']: continue
    
    feats = json.loads(row['features_json'])
    
    # Old prob from database
    old_prob = feats.get('live_prob_buy', 0)
    
    # New prob from freshly trained .pkl
    new_prob = ml_model.predict(feats)
    
    label = row['label']
    
    if old_prob > 0.5:
        old_total += 1
        if label == 1: old_wins += 1
            
    if new_prob > 0.5:
        new_total += 1
        if label == 1: new_wins += 1

old_wr = (old_wins / old_total * 100) if old_total > 0 else 0
new_wr = (new_wins / new_total * 100) if new_total > 0 else 0

print(f"\n--- OLD WR (Live Data Logging) ---")
print(f"Trades: {old_total} | Wins: {old_wins} | WR: {old_wr:.2f}%")

print(f"\n--- NEW WR (Current Model.pkl) ---")
print(f"Trades: {new_total} | Wins: {new_wins} | WR: {new_wr:.2f}%")
