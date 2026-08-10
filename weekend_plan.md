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
- [ ] **Fix Missing ATR Normalization in `feature_builder.py`:**
  - `mom_dist_m5/m15/h1` and `dist_ema_50` were documented in PRD to divide by `ATR`, but code still divides by `last_bid`. Must update formula and regenerate entire historical feature set for v4.1.

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

---

### 5. 🔴 Critical: ATR=0.0 Restart Bug & Calibrator Verdict (Aug 10 Forensic)

#### Bug: `data_buffer` Wipe on Restart → 14min Blind Trading Window
- **Root Cause:** `data_buffer = deque(maxlen=100)` in `main_loop.py` has NO persistence. Every restart wipes all candle history.
- **Impact:** ATR needs 14 candles (14min) to compute. During those 14 minutes after any restart:
  - `ATR = 0.0`, `BB_BW = 0.0`, `RSI = 50.0` (fake neutral), `Stoch = 50.0` (fake neutral)
  - SL/TP calculation uses garbage values → trades get stopped out instantly
  - Model predicts with completely fake indicator features
- **Evidence (Aug 10, `ai-trading` Platt DB):** 3 mid-session restarts at 14:06, 14:37, 14:50 WIB. 479 total ATR=0 snapshots across all days (2.2% of all data). All 5 losing trades (-$55 total) fired during ATR=0 windows.
- **Exists in BOTH codebases** (`ai-trading` AND `ai-trading-iso`).

#### Fix Plan (Priority Order):
- [ ] **Fix A — ATR Floor (Quick, both codebases):**
  - `feature_builder.py` line 33: Change fallback from `0.0` to `1.5`, add `max(atr, 0.5)` floor.
  - `main_loop.py`: Skip trades when `ATR < 0.5` → `"ATR too low, skipping trade"`
- [ ] **Fix B — Buffer Persistence (Proper fix):**
  - On shutdown: serialize `data_buffer` to disk (e.g. `buffer_state.pkl` or SQLite).
  - On startup: reload last buffer state so indicators resume warm without 14min gap.
  - Alternative: request last 100 M1 candles from MT4 EA on startup (EA-side change).
- [ ] **Fix C — ATR Normalization (from §2, still pending):**
  - `mom_dist_m5/m15/h1` and `dist_ema_50` divide by `last_bid` → should divide by `ATR` per PRD.
  - Requires regenerating historical features and retraining. Target: v4.1.

#### Calibrator Verdict: Isotonic > Platt for LightGBM Scalping
- **Platt (sigmoid) failure mode:** LightGBM `max_depth=3` outputs ~20-30 clustered raw probs in a narrow band (0.35-0.50). Platt fits a sigmoid through this narrow cluster → flat zone → only ~5 discrete output values. BUY `coef_` collapsed to 0.0 → BUY completely dead → bot could only SELL into rallies.
- **Isotonic success:** Non-parametric step function captures LightGBM's lumpy miscalibration. Stair-step at 52.96% correctly identified bullish edge → 5/5 wins (+$76).
- **Decision:** Use **Isotonic + 5-Fold KFold OOF** as the production calibrator (`ai-trading-iso`). Deprecate Platt branch.
- **Exception:** If per-session calibrators are re-enabled in future (at N>500/session), use Platt per-session (2-param stability at small N) with Isotonic global.

---

### 6. PRD.md Audit: Mismatches with Isotonic Codebase (Aug 10)

#### 🔴 PRD Says Wrong Things (must fix)
- [ ] **§7 Calibrator recommendation is wrong:** PRD says *"switch to Platt scaling"* — live testing proved Platt collapses on LightGBM. Replace with Isotonic + KFold OOF verdict.
- [ ] **§3 ZMQ ports wrong:** PRD says `5557/5558`, code uses `5567/5568`.
- [ ] **§7 `scale_pos_weight`:** PRD says `is_unbalance=True` or explicit weight. Code hardcodes `1.0` (no imbalance handling). Document whether this is deliberate or a regression.

#### 🟡 PRD Describes Unimplemented Features (mark as deferred)
- [ ] **§4.2 features never built:** `rsi_divergence`, `swept_session_high/low`, `minutes_since_red_folder` — move to Phase 2 in PRD.
- [ ] **§4.2 `spread_atr_ratio`:** PRD says `spread/ATR`. Code outputs raw spread. Either fix code or fix PRD.
- [ ] **§4.2 `hour_utc`:** PRD lists as training feature. Code deliberately drops it before training. Note this in PRD.
- [ ] **§6 Asymmetric Dead Zone:** PRD specifies dual-boundary ranges (SELL: `0.0012-0.0035`, BUY: `-0.0029 to -0.0018`). Code uses simple symmetric `±0.0015`. Either implement or update PRD.

#### 🟡 PRD Describes Unimplemented Infrastructure (mark as planned)
- [ ] **§8 Walk-forward validation:** PRD says 4-5 fold purged walk-forward replaces static split. Code still uses 80/20 static split in `train()`. Offline `walk_forward_validation.py` exists but isn't integrated.
- [ ] **§8 Champion/challenger shadow mode:** Not implemented anywhere.
- [ ] **§10 Drift monitoring (PSI, prediction drift, performance drift):** Not implemented anywhere.

#### ⚠️ weekend_plan.md Internal Inconsistencies
- [ ] **§2 `scale_pos_weight = 1.9`:** Marked `[x]` done, but code uses `1.0`. Either the plan is outdated or the code regressed.
- [ ] **§3 Per-Session Isotonic Calibrators:** Marked `[x]` done, but code has `session_calibrators = {}` (disabled). Update to reflect current state.
- [ ] **§3 Monday Asian SELL-Only / London Cooldown:** Marked `[x]` but not visible in isotonic `main_loop.py`. May only exist in Platt branch — verify and port if needed.

