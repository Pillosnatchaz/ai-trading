# Trading Notes & Market Behavior Logs

## Pre-NY Transition (18:00 - 19:30)
- **Date:** 2026-07-06
- **Observation:** Severe losing streak (17x) due to the AI fighting a strong directional trend.
- **Behavior:** The market shifts from London afternoon chop to pre-NY directional volume. Oscillators (RSI/Stoch) become extremely oversold, tricking mean-reversion models into buying falling knives.
- **Action Taken:** Added a hardcoded H1 trend filter in `main_loop.py` to prevent counter-trend trades.
- **Next Steps:** Monitor if the H1 filter prevents these fakeout losses tomorrow. If not, consider blacklisting the 18:00 - 19:30 window entirely.

---
## Post-Brain Surgery & Geopolitical Shock (July 8-9)
- **Date:** 2026-07-09
- **Observation 1 (The Waterfall):** On July 8, market dropped 800+ pips due to Middle East war escalation. The naked M1 scalper handled it well, only taking 14 trades (-$2) because the probability thresholds blocked the rest. Validates the Gatekeeper concept.
- **Observation 2 (The Asian Grind):** The user enabled the Asian session (08:00 - 12:00 WIB). Result: 1 Win, 15 Losses. The Asian session is a slow creep; price drifts just enough to hit the 30-pip SL without ever triggering the 45-pip TP. Asian session mathematically requires a tighter SL/TP ratio (like 15/20). **Action:** Disabled Asian session indefinitely.
- **Observation 3 (Naked Precision):** Stripping the cheating swing features (`rel_h4`, `rel_d1`) exposed the true noise of M1 trading. Model precision for class 1 plummeted to ~25-29%. This is expected behavior. M1 technicals are a coin flip without macro context.
- **Next Steps:** Proceed with the weekend plan: Optimize SL/TP using grid search and inject `macro_bias` to raise precision.

## First Day of Clean OHLC Data & Grid Search Reality Check
- **Date:** 2026-07-13
- **Observation 1 (The Probability Shift):** Fixed the backtester (`triple_barrier.py`) to be strictly pessimistic (checks high/low, assumes SL hit first). This destroyed the fake 55% win rate and revealed the true baseline win rate of ~34%. Consequence: LightGBM probability outputs dropped to match reality. Lowered the trade execution threshold in `main_loop.py` to `0.45` (45% is a massive edge against a 34% base rate).
- **Observation 2 (Database Poisoning Fix):** MT4 was sending 100 historical candles on startup to build indicators, and Python was accidentally saving all of them to the DB as current duplicates. Fixed by ignoring any candle where `candle_age_seconds > 120` for DB saves. Nuked all 13,356 old rows. DB is now 100% clean.
- **Observation 3 (LLM News Feed):** The Yahoo Finance RSS feed was feeding the LLM useless Canadian mining stock press releases (causing fake BULLISH signals). Switched to `ForexLive` in `config.py` since ForexFactory blocks automated python requests.
- **Observation 4 (Grid Search Winner):** Ran `optimize_sltp.py` on the first batch of flawless OHLC data. `40/60 (1:1.5 Fat)` won the scoreboard. The BUY WR was significantly lower than the SELL WR, proving the market was trending down and highlighting the necessity of having two separate models. 
- **Next Steps:** Hardcoded `40/60` into `run_labeler.py` and `main_loop.py`. The bot will now collect 24/7 data for a full week (5 days) so we have enough statistical density to build a Dynamic ATR-based SL/TP engine this weekend.

---
## Monday Night: The Overfitting Crisis (July 13)
- **Date:** 2026-07-13 (21:00 WIB)
- **Live Performance (before retrain):** London: 25 trades, 56% WR, +$30. Overlap: 10 trades, 50% WR, +$7.50. These used the OLD model trained on 13k rows.
- **Grid Search Result:** `40/60 (1:1.5 Fat)` won. SELL WR: 53.86%, BUY WR: 29.95%. Updated `run_labeler.py` and `main_loop.py` to use 40 SL / 60 TP.
- **The Mistake:** Retrained the ML models on only 750 rows (after nuking the 13k row DB). With `max_depth=5` and `100 estimators`, the AI memorized the tiny dataset and output 94.9% fake confidence. Classic overfitting.
- **The Fix:** Lobotomized the AI in `config.py` (`max_depth=2`, `estimators=20`). Model now predicts "loss" for everything (0% recall). Safe but useless.
- **Also Fixed:** `ml_lightgbm.py` now reads hyperparameters from `config.py` instead of hardcoding them. Changed RSS feed from Yahoo Finance (mining stocks garbage) to ForexLive (actual macro news).
- **Status:** Bot is running in zombie/observation mode. It will collect OHLC data 24/7 but will not execute trades (probabilities too low to trigger the 45% threshold).
- **Action Required (Wed/Thu):** When DB hits 2,000+ rows, bump `LGBM_MAX_DEPTH` to 3 in `config.py` and retrain. When DB hits 4,000+ rows (Friday), restore to `max_depth=4` or `5`.

---
## Tuesday: The News Whipsaw Massacre (July 14)
- **Date:** 2026-07-14 (22:30 WIB)
- **Live Performance:** London: 32 trades, 25% WR, -$36. Overlap: 19 trades, 42% WR, +$2.62.
- **Root Cause:** A Red Folder news event hit at ~12:30 UTC. Price spiked from 4029 to 4087 in ONE MINUTE. The embargo check lived in `llm_macro_agents.py` (runs every 15 min), so `main_loop.py` was blind during the spike. After the spike, the ML saw overbought RSI and started selling aggressively into continuation momentum (SELL 83.9% at 12:46). Classic post-news whipsaw.
- **Fix Applied:** Moved `check_news_embargo()` directly into `main_loop.py` so it checks the ForexFactory calendar **every single tick** (no more blind spots). Extended post-news cooldown from 15 min to 60 min.
- **Friday Plan:** Add `minutes_since_red_folder` as an ML feature so the model *learns* post-news behavior instead of relying on a hard brake.

---
## Wednesday: LLM Role Reassessment & Future Features (July 15)
- **Decision:** Kill LLM macro_bias (news headline sentiment). Replace with candle-based EMA 50/200 cross. The LLM was hallucinating bias from irrelevant articles.
- **Decision:** Keep FF calendar for embargo (hard brake) + add `news_impact` as tiered ML feature (0-3).
- **Scheduled:** Friday night build in `weekend_plan.md`.

### Future LLM Features (Build When Needed)
1. **Trade Journal Analyst (HIGH PRIORITY)** — Feed the LLM the trade history DB and ask: "Why did we lose on Tuesday?" or "What market regime causes the most SELL losses?" It identifies ML blind spots in specific conditions (e.g., "SELL model loses 80% when RSI is 45-55 and hour is 15-17 UTC"). Helps us add targeted features or filters.
2. **Post-Session Debrief** — Auto-generate daily performance summaries (like the ones we paste manually). Run it at 23:00 WIB, save to a log file.
3. **Black Swan Detector** — Scrape Twitter/Reuters for abnormal events (war, pandemic). Not for direction — just triggers "go flat immediately." Safety net for events that technicals can't predict.

---
## Friday Night Build: The Real Model (July 17)
- **Date:** 2026-07-17 (23:30 WIB)
- **Today's Performance:** London: 13 trades, 0% WR, -$39. Overlap: 15 trades, 33% WR, -$7.08.
- **Root Cause:** Old veteran model trained on 20/40 SL/TP was executing 40/60 trades. The probability math was fundamentally wrong — it predicted wins for 20-pip scalps while holding for 60 pips.

### Changes Made
1. **Config cleaned:** Removed all LLM/Ollama/DeepSeek settings. No more external dependencies for macro bias.
2. **ML restored to full power:** `LGBM_MAX_DEPTH=5`, `LGBM_ESTIMATORS=100`.
3. **Retrained on 4,296 rows** with correct 40/60 SL/TP labels.
   - BUY: Baseline 67.6%, Accuracy 61.1%, Trades 126/859 (14.7%)
   - SELL: Baseline 60.4%, Accuracy 58.7%, Trades 171/859 (19.9%)
4. **Candle-based macro_bias:** Uses EMA 50 slope instead of LLM. No RSS, no Ollama, no hallucinations.
5. **Cold start fix:** Old candles now warm up indicators (RSI/EMA) without being saved to DB.
6. **Backups saved:** `backups/17-07-2026/`

### Still TODO
- [ ] Add `minutes_since_red_folder` as ML feature
- [ ] Add `news_impact` (0-3) from FF calendar as ML feature
- [ ] Build Trade Journal Analyst (LLM for post-session analysis)
- [ ] Fibonacci OTE for dynamic SL/TP

---
## Tuesday: Tick vs M1 Design Note (July 21)

### Why we run on M1 candle closes (not every tick)
- ML was trained on M1 data. Feeding it ticks = different distribution = garbage predictions.
- Indicators (RSI, Stochastic, EMA) jitter 200x per minute on ticks. One clear signal per candle > 200 conflicting ones.
- 40/60 SL/TP is calibrated for M1 volatility, not tick noise.

### What we're missing on M1-only
- Entry timing: we enter at candle close, but the optimal price might have been mid-candle.
- Fast moves: a 30-pip spike and reversal within one M1 candle is invisible to us.
- Sub-minute patterns: aggressive institutional order flow shows up in ticks before candles confirm.

### Future approach: M1 for decision, ticks for execution
- Use M1 candle close to decide BUY/SELL/SKIP (the brain).
- Once a decision is made, use tick data to time the actual entry within the next 1-2 candles (the trigger).
- Example: ML says "BUY next candle" → wait for a tick-level dip within that candle → enter at better price.
- This is a Phase 2 optimization. Get the M1 model profitable first.

---
## Wednesday: BUY Model Crisis & Feature Ideas (July 23)
- **BUY performance:** 17 trades, 2 wins, 15 losses = 11.7% WR. Model probabilities uncorrelated with outcomes.
- **SELL performance:** holding steady, carrying profitability.
- **Decision:** Let it run on demo through Thursday to confirm pattern, then fix on weekend.

### Weekend BUY Fix Plan
- [ ] Run `optimize_sltp.py` for BUY-only — find if different SL/TP works better
- [ ] Consider separate thresholds (BUY 0.55, SELL 0.45) — but only if probability becomes meaningful
- [ ] If BUY stays broken: disable BUY, trade SELL-only until model is fixed

### Future Feature: Tick Volume (Phase 3)
- **Tick count per M1 candle** — high volume confirms moves, low volume = fakeout. MT4 `iVolume()` provides this.
- **Blocker:** No historical tick data in DB. Need to start collecting now, wait 2-3 weeks, then retrain.
- **Implementation:** Add `tick_volume` to the EA's JSON payload, save in features_json, use as ML feature after enough data.
- **Skip:** Buy/sell pressure (noisy on retail data), microstructure (HFT territory, not useful for M1).

---
---
## Wednesday Full Day Results (July 23)
- **London:** 37 trades, 59.46% WR, +$72.90 — best London yet
- **Overlap:** 70 trades, 38.57% WR, -$36.33 — late session bleed
- **Net:** +$36.57
- **Peak:** ~+$80 before 22:00 WIB. 14-trade lose streak near close wiped half the gains.

### Key Findings
- BUY spammed 174 signals (vs 60 SELL). H1 filter blocked 60% but ~67 still got through.
- 88 SELL signals fired after 22:00 WIB — every minute near close. Low liquidity + wide spreads = death.
- **Action needed:** Consider cutting session end from 23:00 to 22:00 WIB to avoid late-session bleed.
- **No cooldown = too many trades.** 70 trades in Overlap is excessive. Need some throttle.

---
*(Add future notes below)*
