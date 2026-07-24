import sys
import os
sys.path.insert(0, r"G:\Projects\ai-trading")

import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import accuracy_score
from intelligence.ml_lightgbm import LightGBMPredictor

def run_walk_forward_validation(direction='buy', n_splits=5, embargo_bars=120):
    print(f"\n==================================================")
    print(f" PURGED, EMBARGOED WALK-FORWARD VALIDATION ({direction.upper()})")
    print(f" ({n_splits} Rolling Folds | {embargo_bars}-Bar Embargo Gap)")
    print(f"==================================================")

    predictor = LightGBMPredictor(direction=direction)
    df = predictor.fetch_training_data()

    if df is None or len(df) < 500:
        print("[!] Insufficient data for walk-forward validation (minimum 500 rows required).")
        return

    X = df.drop(columns=['target_label'])
    y = df['target_label']

    total_samples = len(X)
    fold_size = total_samples // (n_splits + 1)

    results = []

    for fold in range(1, n_splits + 1):
        train_end_idx = fold * fold_size
        test_start_idx = train_end_idx + embargo_bars
        test_end_idx = min(total_samples, test_start_idx + fold_size)

        if test_start_idx >= total_samples or (test_end_idx - test_start_idx) < 50:
            break

        X_train = X.iloc[:train_end_idx]
        y_train = y.iloc[:train_end_idx]

        X_test = X.iloc[test_start_idx:test_end_idx]
        y_test = y.iloc[test_start_idx:test_end_idx]

        n_neg = (y_train == 0).sum()
        n_pos = (y_train == 1).sum()
        pos_weight = (n_neg / n_pos) if n_pos > 0 else 1.9

        model = lgb.LGBMClassifier(
            n_estimators=100,
            learning_rate=0.05,
            max_depth=5,
            scale_pos_weight=pos_weight,
            random_state=42,
            verbose=-1
        )
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        probs = model.predict_proba(X_test)[:, 1]
        
        acc = accuracy_score(y_test, y_pred)
        baseline = (y_test == 0).sum() / len(y_test)
        lift = acc - baseline

        # Probability calibration check on >= 0.45 threshold
        threshold_mask = probs >= 0.45
        if threshold_mask.sum() > 0:
            signals_taken = threshold_mask.sum()
            wins_taken = (y_test[threshold_mask] == 1).sum()
            signal_wr = (wins_taken / signals_taken) * 100
        else:
            signals_taken = 0
            signal_wr = 0.0

        results.append({
            'fold': fold,
            'train_n': len(X_train),
            'test_n': len(X_test),
            'baseline_acc': round(baseline * 100, 2),
            'model_acc': round(acc * 100, 2),
            'lift_pct': round(lift * 100, 2),
            'signals_0.45': signals_taken,
            'signal_wr_pct': round(signal_wr, 2)
        })

    res_df = pd.DataFrame(results)
    print(res_df.to_string(index=False))
    
    avg_acc = res_df['model_acc'].mean()
    avg_lift = res_df['lift_pct'].mean()
    avg_sig_wr = res_df[res_df['signals_0.45'] > 0]['signal_wr_pct'].mean()
    
    print(f"\n--- WALK-FORWARD SCOREBOARD ({direction.upper()}) ---")
    print(f"  - Average Model Accuracy:  {avg_acc:.2f}%")
    print(f"  - Average Lift over Base:  {avg_lift:+.2f}%")
    print(f"  - Average Signal Win Rate: {avg_sig_wr:.2f}% (on prob >= 0.45)")

if __name__ == "__main__":
    run_walk_forward_validation(direction='buy', n_splits=5)
    run_walk_forward_validation(direction='sell', n_splits=5)
