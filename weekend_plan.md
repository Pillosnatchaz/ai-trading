# 📉 The Lazy Senior Dev Weekend Plan

---

### 1. Completed & Verified System Upgrades (MIA v4.0 Engine)
- [x] **Triple Barrier High/Low Labeling:** `data_engine/triple_barrier.py` checks M1 High/Low for pessimistic SL/TP evaluation.
- [x] **Candle-Based Macro Bias:** `main_loop.py` derives macro trend directly from `ema_50_slope` (no LLM, no RSS, zero latency).
- [x] **Indicator Warmup Cold-Start Fix:** Historical startup candles warm up EMA/RSI buffers immediately without trading on old bars.
- [x] **22:00 WIB Late-Session Cutoff:** Hard cutoff enforced in `main_loop.py` to stop late-night spread bleed.
- [x] **Minute-Level Snapshot Deduplication:** SQL window functions enforce 1 clean row per M1 candle close, eliminating time-horizon distortions.
- [x] **Database Lock & Single Position Guard:** Added `timeout=30.0` and 180s trade cooldown to prevent position stacking.
- [x] **30-Minute News Calendar Caching:** In-memory schedule caching fetches ForexFactory XML at most twice per hour to prevent HTTP 429 rate limits.

---

### 2. Pipeline Audit & Feature Engineering Sprint
- [ ] **Fix Label Squashing in `ml_lightgbm.py`:**
  - Filter out `-2 (Fast SOTW)` rows during training so model learns clean wins (`+1`) vs clean losses (`-1`).
- [ ] **Add Class Imbalance Handling (`scale_pos_weight`):**
  - Pass `scale_pos_weight = 1.9` in `LGBMClassifier` so trees weight winning setups equally.
- [ ] **Fix FVG Feature (`dist_to_fvg = 9999`):**
  - Split into `has_fvg` (1/0 binary) and `dist_to_fvg` (`np.nan` when no active FVG exists) to eliminate arbitrary `9999` split distortion.

---

### 3. Session-Specific Architecture Sprint (24/7 Session Profitability)
- [ ] **Monday Asian SELL-Only Rule (08:00 – 12:00 WIB):**
  - Empirical audit of 468 snapshots proved Monday Asian SELL win rate is **48.46%** (+EV winner), while BUY win rate is **18.05%** (drag trap).
  - Implementation in `main_loop.py`: Enable `MONDAY_ASIA` session for SELL signals only (force `prob_buy = 0.0`).
- [ ] **15-Minute London Open Cooldown (14:00 – 14:15 WIB):**
  - Empirical WIB audit proved 14:00 WIB London opening spike causes initial fakeout losses (11 losses / 3 wins).
  - Implementation in `main_loop.py`: Pause trade entries from 14:00 to 14:15 WIB to let London's opening candle range settle before entering.
- [ ] **Per-Session Dedicated LightGBM Models (`model_london`, `model_ny`, `model_asia`):**
  - Database audit proved London (+ $133.65) vs NY (- $75.03) have opposing market dynamics (London trend expansion vs NY news mean-reversion).
  - Train 3 dedicated LightGBM predictor pairs in `intelligence/ml_lightgbm.py`:
    - `model_london`: Trained on 14:00 – 19:30 WIB data (trend expansion specialist).
    - `model_ny`: Trained on 19:30 – 22:00 WIB data (news volatility & mean-reversion specialist).
    - `model_asia`: Trained on 08:00 – 12:00 WIB data (range-bound micro-scalp specialist).
  - `main_loop.py` routes live tick features to the corresponding session model pair based on current WIB time.
- [ ] **Dynamic Per-Session SL/TP Scaling (ATR Multipliers):**
  - Adjust SL/TP ATR multipliers in `main_loop.py` based on active session volatility:
    - **London:** 1.3x ATR SL / 2.0x ATR TP (35 / 55 pips).
    - **NY Overlap:** 2.0x ATR SL / 3.0x ATR TP (60 / 90 pips — stops US news noise from suffocating trades).
    - **Asia:** 1.0x ATR SL / 1.5x ATR TP (20 / 30 pips — tight range scalps).
