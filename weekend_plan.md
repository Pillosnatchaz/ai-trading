**Ponytail: Weekend Sprint DONE. Here's the summary.**

### What was built:

| Task | Status | What Changed |
|------|--------|-------------|
| **1. Triple Barrier OHLC Fix** | Γ£à | `triple_barrier.py` now uses High/Low for pessimistic SL/TP checking |
| **2. Grid Search** | Γ£à | `optimize_sltp.py` created ΓÇö tested 7 SL/TP combos. Winner: 1:2 ratio |
| **3. DB Schema** | Γ£à | `database.py` + `main_loop.py` now save High/Low per candle |
| **4. News Embargo** | Γ£à | `llm_macro_agents.py` checks ForexFactory for Red Folder events |
| **5. Embargo Gate** | Γ£à | `main_loop.py` blocks all trades when `news_embargo == true` |
| **6. Stale Data Protection** | Γ£à | If `macro_state.json` is >60 min old, forces `NEUTRAL` |
| **7. ML Integration** | Γ£à | `macro_bias` encoded as -1/0/1 and fed to LightGBM |
| **8. Model Retrained** | Γ£à | BUY: 67% acc, SELL: 58% acc (now with macro_bias feature) |

### Monday Checklist:
1. Start `main_loop.py` ΓÇö it will now save OHLC data and use the new models
2. Start `llm_macro_agents.py` ΓÇö make sure Ollama is running first
3. Let it collect data all day, then re-run `optimize_sltp.py` Monday night with real OHLC data

==============================

# 📉 The Lazy Senior Dev Weekend Plan (Updated July 10)

## Saturday Morning: Fix the Backtest Engine

### 1. Fix `triple_barrier.py` — Use High/Low, Not Close
The current labeler only checks M1 Close prices. In real life, price can hit your SL mid-candle and bounce back by close. This makes the backtest optimistic and unreliable.
- **Fix:** Check High and Low of each M1 candle against SL/TP thresholds.
- **Pessimistic Rule:** If both SL and TP are breached in the same candle, assume SL hit first (worst case).
- **Why:** If a setup survives this pessimistic test, it's bulletproof for live trading.

### 2. Run the SL/TP Grid Search (`optimize_sltp.py`)
Using the fixed `triple_barrier.py`, simulate multiple SL/TP setups against the same historical data:
- 30 SL / 45 TP (Current baseline)
- 20 SL / 30 TP (Tight 1:1.5)
- 30 SL / 60 TP (1:2 ratio)
- 40 SL / 60 TP (Wide 1:1.5)

Output a scoreboard: Win Rate, Net Profit, and SOTW count for each setup. Pick the winner.

### 3. Retrain the ML Models
After picking the best SL/TP from the grid search, re-run `run_labeler.py` with the winning ratio and retrain both BUY and SELL models.

---

## Saturday Afternoon: Wire Up the LLM

### 4. Isolate the LLM (Phase 5)
Build and test `intelligence/llm_macro_agents.py`.
- **Task 1 (Sentiment):** Pull an RSS feed (e.g., ForexFactory), send to Ollama (DeepSeek), get Bullish/Bearish bias.
- **Task 2 (News Brake):** Have Ollama flag `news_embargo: true` if there is a Red Folder event (CPI, NFP, FOMC) within 30 minutes.
- **Task 3 (Gatekeeper Update):** Update `main_loop.py` to `continue` (skip trading) if `news_embargo == true` to survive whipsaws.
- **Task 4 (ML Integration):** In `ml_lightgbm.py`, encode the strings: `df['macro_bias'] = df['macro_bias'].map({'BEARISH': -1, 'NEUTRAL': 0, 'BULLISH': 1})` and remove it from the `drop` list.
- **Task 5 (Stale Data Protection):** In `feature_builder.py`, check the modified time of `macro_state.json`. If older than 60 mins (Ollama dead/off), forcefully overwrite `macro_bias` to `NEUTRAL` to prevent ghost signals.

---

## Sunday: Validate & Deploy

### 5. The Monday Execution
Before leaving for work on Monday, start two separate processes:
1. `main_loop.py` (Fast tick data collection)
2. `llm_macro_agents.py` on a 15-minute cron/loop (Slow macro sentiment collection)

By Monday night, you will have a clean dataset of technical features and a synchronized log of LLM macro decisions.

---

## Rules
- **Zero UI.** The bot runs headless. No dashboards.
- **No Asian Session.** London + Overlap only until we build a dedicated Asian model.
- **No M30 features.** M15 + H1 already cover it. Don't touch the MT4 bridge.
- **Keep macro_bias as 3 states only.** BULL / NEUTRAL / BEAR. LightGBM calculates intensity from technicals.

---

## Monday Night (Post-Market) Tasks
1. Stop the bot.
2. Open `optimize_sltp.py`.
3. Change line 15 back to:
   `df = pd.read_sql_query("SELECT price, high, low FROM snapshots WHERE high IS NOT NULL ORDER BY id ASC", conn)`
4. Run `py optimize_sltp.py`. This will now ONLY run on the flawless OHLC data collected on Monday.
5. Review the scoreboard and make the final decision on the static SL/TP ratio before we start building the Dynamic ATR SL/TP logic on Tuesday.

---

## Friday Night (Post-Market) Tasks — Dynamic SL/TP Build
**Prerequisite:** DB must have 4,000+ rows of clean OHLC data.

### 1. Restore ML Power
- In `config.py`, set `LGBM_MAX_DEPTH = 5` and `LGBM_ESTIMATORS = 100`.
- Backup current `.pkl` files first!
- Run `run_labeler.py` then retrain both BUY and SELL models.

### 2. Build Dynamic SL/TP Engine (Fibonacci OTE + ATR)
- Calculate M15/H1 swing highs and swing lows from the data bridge.
- Use Fibonacci extensions (-27.2%, -61.8%) on those swings to set dynamic TP targets.
- Use ATR to set dynamic SL (e.g., `SL = ATR * 1.5`, minimum 20 pips).
- Enforce minimum 1:1.5 Risk/Reward ratio (if Fib TP < SL * 1.5, skip the trade).

### 3. Backtest Dynamic vs Static
- Upgrade `optimize_sltp.py` to simulate dynamic Fibonacci TP alongside the static setups.
- Compare Net$/100 to see if dynamic beats the 40/60 winner.
- Only deploy to live if dynamic wins the scoreboard.

### 4. News-Aware ML Feature
- Add `minutes_since_red_folder` as a feature in `main_loop.py` (save to features_json).
- Calculated from the inline embargo check already in main_loop.py.
- Values: 0-999 (0 = news happening now, 60 = 1 hour after, 999 = no news today).
- This teaches LightGBM that trading 5 min after CPI is fundamentally different from trading 2 hours later.
- The ML learns post-news behavior instead of relying on a hard 60-min brake.

### 5. Kill LLM Macro Bias — Replace with Candle-Based Bias
**Rationale:** The LLM reads news headlines and hallucinates a bias. Candles don't lie.

**New architecture:**
| Component | Source | Purpose |
|-----------|--------|---------|
| `macro_bias` | EMA 50/200 cross from collected candles | BULLISH/BEARISH/NEUTRAL direction |
| `news_impact` | FF calendar `<impact>` tag | ML feature (0=none, 1=low, 2=medium, 3=high) |
| `news_embargo` | FF calendar + time math | Hard brake for High impact events |

**Delete:**
- Ollama / DeepSeek dependency (no more local LLM needed for trading)
- RSS headline fetching from ForexLive/Yahoo
- `macro_state.json` file
- LLM prompt engineering in `llm_macro_agents.py`

**Keep in `llm_macro_agents.py`:**
- `check_news_embargo()` function (but it's now also inline in main_loop.py)
- Or delete the file entirely and keep everything inline

### 6. Fix Indicator Warmup (Cold Start Bug)
**Problem:** MT4 sends 100 historical candles on startup for indicator warmup, but `candle_age_seconds > 120` filter throws them ALL away (including from the indicator buffer). After a restart, RSI/Stochastic/EMA are garbage until 50+ live candles arrive.
**Fix:** Use old candles for indicator buffer warmup but skip DB save and trading:
```python
if candle_age_seconds > 120:
    price_buffer.append(candle_data)  # warm up indicators
    last_candle_id = current_candle_id
    continue  # don't save to DB or trade
```

### 7. Model Calibration & Pipeline Audit Upgrades (July 24 Empirical Audit)
**Rationale:** Database audit of 5,804 rows & live trade logs proved probability calibration collapse.

- [ ] **Fix Label Squashing in `ml_lightgbm.py`:**
  - Currently `1 if label == 1 else 0` squashes 28% Fast SOTW (`-2`) noise stops into clean losses (`0`), ruining probability calibration.
  - Fix: Filter out `-2 (Fast SOTW)` rows during training so model learns clean wins (`+1`) vs clean losses (`-1`).
- [ ] **Add Class Imbalance Handling (`scale_pos_weight`):**
  - Raw win rate is ~34% (minority class). Pass `scale_pos_weight = 1.9` in `LGBMClassifier` so trees treat winning setups with equal weight.
- [ ] **Fix FVG Feature (`dist_to_fvg = 9999`):**
  - In `feature_builder.py`, split into `has_fvg` (1/0 binary) and `dist_to_fvg` (`np.nan` when no active FVG exists) to eliminate arbitrary `9999` split distortion.
- [ ] **Enforce 22:00 WIB Late-Session Cutoff:**
  - In `main_loop.py`, cut session end from 23:00 to 22:00 WIB to avoid low-liquidity late-night spread bleed.
