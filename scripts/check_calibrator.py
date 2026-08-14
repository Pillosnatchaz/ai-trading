import joblib
import numpy as np
import glob
import os

# Find latest BUY model
buy_models = glob.glob(r'E:\Projects\ai-trading-iso\intelligence\lgbm_model_buy.pkl*')
if not buy_models:
    print("No buy model found")
else:
    latest = max(buy_models, key=os.path.getmtime)
    print(f"Loading {latest}")
    m = joblib.load(latest)
    
    print(f"Keys in model dict: {m.keys()}")
    calibrator = m.get('calibrator') or m.get('global_calibrator')
    if calibrator:
        print("\nBUY Isotonic Calibrator Steps (Raw Prob -> Calibrated Prob):")
        # Generate some dummy probabilities from 0 to 1
        test_probs = np.linspace(0.2, 0.8, 20)
        calibrated = calibrator.predict(test_probs)
        for raw, cal in zip(test_probs, calibrated):
            print(f"Raw: {raw:.3f} -> Calibrated: {cal:.3f}")
    else:
        print("No calibrator found in model dict.")

