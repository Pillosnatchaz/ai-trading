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
- [x] **Fix Label Squashing in `ml_lightgbm.py`:**
  - Filter out `-2 (Fast SOTW)` rows during training so model learns clean wins (`+1`) vs clean losses (`-1`).
- [x] **Add Class Imbalance Handling (`scale_pos_weight`):**
  - Pass `scale_pos_weight = 1.9` in `LGBMClassifier` so trees weight winning setups equally.
- [x] **Fix FVG Feature (`dist_to_fvg = 9999`):**
  - Split into `has_fvg` (1/0 binary) and `dist_to_fvg` (`np.nan` when no active FVG exists) to eliminate arbitrary `9999` split distortion.

---

### 3. Session-Specific Middle-Ground Architecture (Current 8.9k Rows)
- [x] **Global LightGBM Trees + Per-Session Isotonic Calibrators:**
  - Keep 2 global LightGBM models (`model_buy` & `model_sell`) trained on full 8,900+ dataset to prevent data starvation (~800 rows per session split).
  - Fit **separate Isotonic Calibrators per session** (`calibrator_london`, `calibrator_ny`, `calibrator_asia`) so probabilities calibrate accurately to session-specific win rates without starving base trees of data.
- [x] **Statistical Discipline Guard (Sample Size Rule):**
  - **Rule:** Do NOT alter live probability thresholds based on small-$n$ single-week buckets ($n < 100$). Accumulate bucket data until each bin hits $n \ge 100+$.
  - **Cross-Tab Finding:** Cross-tab audit proved the `0.45 - 0.50` SELL bucket achieved **51.1% WR (+ $138.89 P&L)** in London, but dropped to **35.7% WR (- $30.08 P&L)** in NY Overlap. NY drag is session/ATR driven, NOT a threshold flaw.
- [x] **Dynamic Per-Session SL/TP Scaling (ATR Multipliers):**
  - Adjust SL/TP ATR multipliers in `main_loop.py` based on active session volatility:
    - **London:** 1.3x ATR SL / 2.0x ATR TP (35 / 55 pips).
    - **NY Overlap:** 2.0x ATR SL / 3.0x ATR TP (60 / 90 pips — stops US news noise from suffocating trades).
    - **Asia:** 1.0x ATR SL / 1.5x ATR TP (20 / 30 pips — tight range scalps).
- [x] **Monday Asian SELL-Only Rule (08:00 – 12:00 WIB):**
  - Empirical audit of 468 snapshots proved Monday Asian SELL win rate is **48.46%** (+EV winner), while BUY win rate is **18.05%** (drag trap).
  - Implementation in `main_loop.py`: Enable `MONDAY_ASIA` session for SELL signals only (force `prob_buy = 0.0`).
- [x] **15-Minute London Open Cooldown (14:00 – 14:15 WIB):**
  - Empirical WIB audit proved 14:00 WIB London opening spike causes initial fakeout losses (11 losses / 3 wins).
  - Implementation in `main_loop.py`: Pause trade entries from 14:00 to 14:15 WIB to let London's opening candle range settle before entering.

* **Long-Term Roadmap (Phase 3 @ 50k+ Rows):** Once database reaches 50,000+ clean snapshots, run `walk_forward_validation.py` to evaluate dedicated per-session models (`model_london`, `model_ny`, `model_asia`).

---

### 4. LLM & Local AI Agent Experiments (Ollama / DeepSeek)
- [x] **LLM Post-Mortem Trade Diagnostician (`intelligence/llm_trade_auditor.py`):**
  - Triggered on trade loss: sends trade features, entry/exit prices, and candle snippet to local Ollama (`deepseek-r1`).
  - Classifies root cause (`COUNTER_TREND_FAKEOUT`, `SPREAD_EXPANSION`, `NEWS_WHIPSAW`) and saves diagnosis to `live_trades` DB.
- [x] **LLM Weekly Performance Summarizer (`scripts/llm_weekly_report.py`):**
  - Runs Friday night: queries `live_trades` and `snapshots` for the week (Win Rate, P&L, London vs NY metrics, hourly stats).
  - Passes aggregated data to Ollama to generate an executive Markdown report in `reports/weekly_summary_YYYY_MM_DD.md`.

