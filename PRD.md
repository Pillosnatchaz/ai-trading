# PRD: MIA v4.0 — LightGBM-Driven XAUUSD Scalping System
**Status:** Living document (last audit: Aug 10, 2026)
**Supersedes:** MIA v3.0
**Author context:** Rebuild informed by v3.0 live/historical diagnostics (BUY model collapse, SELL inverse-calibration finding, label-squashing leak, session-transition losses)

---

## 1. Problem Statement & Goals

MIA v3.0 proved the core architecture (ZMQ bridge, dual LightGBM engine, Triple Barrier labeling, news embargo) is sound, but live performance diverged sharply from backtest on the BUY side (11.7% live WR vs ~34% historical), and diagnostics surfaced a second, previously-hidden problem: SELL's own historical calibration curve is *inverted* (confidence anti-correlates with win rate). Several root causes were identified but never fixed:

1. Triple Barrier's 5-class label (`+1/-1/0/-2/-3`) is collapsed to binary `0/1` before training, discarding SOTW (stopped-out-then-win) information — disproportionately punishing BUY.
2. `dist_to_fvg` uses a `9999` sentinel instead of a proper missing-value representation.
3. `rel_m5/m15/h1` are mislabeled "Structure" when they are actually normalized momentum/distance features — this has been actively misleading feature-importance interpretation.
4. No dynamic SL/TP — fixed 40/60 pips regardless of volatility regime.
5. No walk-forward validation — single static 80/20 split, so regime-conditional instability (confirmed via the SELL inverse-calibration finding) went undetected.
6. No session-transition awareness, despite an observed empirical pattern of London-to-NY reversal causing correlated losses.
7. **Confirmed model version mismatch:** Historical `live_trades` aggregated 46 retrain iterations across 3 weeks, causing historical audit logs to compare multiple distinct model generations.
8. No class-imbalance handling in LightGBM despite a ~34% minority "win" class.

**Goal of v4.0:** Fix the above with minimal architectural upheaval — this is a targeted rebuild of the labeling, feature, validation, and calibration layers, not a rewrite of the ZMQ/execution plumbing that already works.

**Non-goals (explicitly out of scope for v4.0):**
- Order-flow / true traded-volume data (not available from retail MT4/5 feeds without a paid L2 add-on — flagged as a future consideration, not a v4.0 deliverable)
- Multi-instrument generalization (v4.0 stays XAUUSD-only)
- Full four-model regime/quality-grading architecture proposed by external review — deferred until the two-model system is properly calibrated and stable (see §9, Phased Roadmap)

---

## 2. Guiding Principles (non-negotiable this time around)

1. **Every feature must be independently sanity-checked before being trusted in the model.** No feature ships without (a) a "liveness rate" check (what % of bars does it fire on — flag anything >20–30% as likely too loose to be selective) and (b) a visual spot-check against real charts for structural features (FVG/OB/sweeps).
2. **Label information is never discarded before training without an explicit, logged decision.** The SOTW classes exist because they carry real information; every squashing/collapsing step must be justified and A/B tested against the alternative.
3. **No feature is labeled with trading jargon it doesn't actually implement.** ("Structure" must mean BOS/CHOCH, not price distance.)
4. **Validate BUY and SELL as if they were two separate research projects.** Symmetry is assumed nowhere — it's tested everywhere (identical code-path audits, independent calibration curves, independent walk-forward folds).
5. **Static single-split validation is banned.** Every model change is evaluated walk-forward, across at least 4–5 chronological folds, before being considered for live deployment.
6. **Model version is always traceable.** Every live prediction is logged with the exact model artifact hash/version that produced it — the "which model made this live trade" ambiguity from v3.0 must never recur.

---

## 3. System Architecture

```mermaid
flowchart TD
    MT5["MetaTrader 4/5 EA"] -->|ZMQ PUB 5567: M1 candles + ticks| ORCH["Python Orchestrator"]
    ORCH -->|ZMQ PUB 5568: signal + dynamic SL/TP| MT5

    ORCH --> FEAT["Feature Engine"]
    FEAT --> STRUCT["Structural/SMC Module\n(FVG, session sweep — swing-based)"]
    FEAT --> MOM["Momentum/Distance Module\n(EMA, RSI, rel_* renamed honestly)"]
    FEAT --> VOL["Volatility Module\n(ATR, BB, regime bucket)"]
    FEAT --> MICRO["Microstructure Module\n(spread, wick/body ratio, tick velocity)"]
    FEAT --> TIME["Time/Session Module\n(session id, mins_to_transition, kill zones)"]

    ORCH --> EMBARGO["News Embargo (ForexFactory XML)"]
    ORCH --> REGIME["Regime Gate\n(H1 trend filter, volatility bucket, session filter)"]
    ORCH --> ML["Dual LightGBM Engine\n(BUY model | SELL model)\nclass-imbalance aware"]
    ORCH --> CALIB["Probability Calibration Layer\n(Isotonic + KFold OOF, per-direction)"]
    ORCH --> RISK["Risk Engine\n(ATR & Swing-based dynamic SL/TP,\nfixed-fractional sizing)"]
    ORCH --> DB[("SQLite (ai_data.db)\nfeatures + labels + model_version + live outcomes")]

    ORCH -.-> MONITOR["Drift Monitor (PLANNED)\n(feature PSI, prediction drift,\nrolling live calibration)"]
    MONITOR -.-> RETRAIN["Retrain Pipeline (PLANNED)\n(walk-forward, champion/challenger)"]
```

Key changes from v3.0: a **Regime Gate** and **Calibration Layer** are now explicit pipeline stages (not buried inside `main_loop.py` as ad hoc thresholds), and a standing **Drift Monitor** feeds a formal **Retrain Pipeline**.

---

## 4. Feature Engineering Spec

### 4.1 Fixes to carry over from v3.0 (mandatory, not optional)

| Feature | v3.0 issue | v4.0 fix |
|---|---|---|
| `dist_to_fvg` | `9999` sentinel conflates absence with distance | Split into `has_fvg` (binary) + `fvg_dist_atr` (NaN when absent — LightGBM handles native NaN splits) |
| `rel_m5/m15/h1` | Labeled "Structure," is actually momentum/distance | Rename to `mom_dist_m5/m15/h1`. Category = "Momentum," not "Structure" |
| FVG / OB (if reintroduced) | No mitigation/expiry tracking | Add `mitigated` flag; once price trades back through, feature deactivates same-bar |
| Single-Candle OTE | Computed from single M1 candle high/low, not confirmed swing legs — pure noise | Replaced by multi-candle Swing High / Low detector (`get_swing_levels`, lookback=20) for dynamic SL/TP & sizing |

### 4.2 Full feature table (v4.0)

| Feature | Category | Formula / Logic | Notes |
|---|---|---|---|
| `atr` | Volatility | 14-SMA of True Range, floor=0.5, fallback=1.5 | Used for SL/TP sizing. **ATR=0.0 cold-start bug fixed Aug 10.** |
| `bb_pctb`, `bb_bw` | Volatility | Standard Bollinger %B / bandwidth | ✅ Implemented |
| `rsi` | Momentum | Standard RSI (14) | ✅ Implemented |
| `stoch_k` | Momentum | Standard (14,3,3) | ✅ Implemented |
| `dist_ema_50`, `ema_50_slope` | Momentum | `(Bid-EMA)/ATR`; 5-bar ROC of EMA | ✅ Implemented. ATR normalization applied Aug 10. |
| `mom_dist_m5/m15/h1` | Momentum (renamed) | `(Bid - Close_TF)/ATR` | ✅ Implemented. ATR normalization applied Aug 10. |
| `has_fvg`, `fvg_dist_atr` | Structural | See §4.1 | ✅ Implemented |
| `spread` | Microstructure | Raw bid-ask spread | ✅ Implemented. ⚠️ Not ATR-normalized (PRD originally specified `spread_atr_ratio`) |
| `wick_body_ratio` | Microstructure | (upper+lower wick) / body size, current candle | ✅ Implemented |
| `tick_volume` | Microstructure | M1 tick count fetched natively via MT4 `iVolume()` | ✅ Implemented |
| `session` | Time/Regime | categorical: ASIAN/LONDON/OVERLAP | ✅ Implemented (22:00 WIB cutoff enforced) |
| `mins_to_session_transition` | Time/Regime | continuous countdown to next session boundary | ✅ Implemented |
| `macro_bias` | Regime | slope-based BULLISH/BEARISH/NEUTRAL flag | ✅ Implemented, derived from EMA 50 slope |
| `volatility_regime` | Regime | categorical bucket from ATR thresholds (LOW/NORMAL/HIGH) | ✅ Implemented |
| `swing_high`, `swing_low` | Structural | 20-bar max/min for dynamic SL placement | ✅ Implemented |
| `live_prob_buy/sell` | Audit only | model output | **hard rule: never joins the training feature set** ✅ |

#### Deferred to Phase 2 (not yet implemented)
| Feature | Category | Notes |
|---|---|---|
| `rsi_divergence` | Momentum | Price lower-low vs RSI higher-low. Cheap addition but not built yet. |
| `swept_session_high/low` | Structural (liquidity sweep) | Requires tracking prior session H/L. Key for London→NY reversal pattern. |
| `minutes_since_red_folder` | Time/News | Would teach LightGBM post-news volatility. News embargo currently binary (trade/don't trade). |
| `hour_utc` | Time | Extracted in training pipeline but deliberately **dropped** before model training — model uses session-based features instead. |

### 4.3 SMC features explicitly deferred, not abandoned

- **Multi-candle Swing Leg Detection (`get_swing_levels`)**: INCLUDED in Phase 1 / Sprint 2. Evaluates 20-bar fractal Swing Highs ($\max$) and Swing Lows ($\min$) to calculate:
  1. Structural Dynamic Stop Loss (placed 2 pips beyond recent Swing High/Low).
  2. Dynamic Position Sizing: $\text{Lot Size} = \frac{\text{Risk Dollars}}{\text{SL Pips} \times \text{Pip Value}}$.
- **Single-candle OTE / Fib**: Single-candle OTE is dropped. Multi-candle Fibonacci Extensions (-27.2%, -61.8%) off fractal swing legs are used for structural Take Profit targets.
- **Order Blocks**: Deferred — needs mitigation tracking and a real swing-based definition, not just "last counter-candle before impulsive move" without invalidation logic.
- **BOS/CHOCH**: Not yet implemented in any version — genuinely deferred to a future phase (§9), since it requires proper swing-sequence logic.

---

## 5. Labeling & Target Definition

### 5.1 Triple Barrier — keep the mechanism, fix the mapping

Keep: pessimistic OHLC evaluation (assume SL hit first when a single candle's range breaches both), and the 5-class taxonomy (`+1/-1/0/-2/-3`).

**Fix the collapse.** Rather than the blanket `1 if label==1 else 0` used in v3.0, v4.0 uses:

- **Primary approach (Option A — exclusion):** Drop `-2` (Fast SOTW, ≤15 bars) rows from training entirely — these are noise-dominated and their inclusion as "losses" actively teaches the model to avoid setups that were directionally correct.
- `-3` (Slow SOTW) is **kept as a loss (`0`)** — by definition this was a real drift/timing miss even if eventually right, and including it as a loss keeps the model honest about entries that took too long to resolve.
- `0` (timeout) is **kept as a separate diagnostic dimension**, not folded blindly into losses — track timeout rate per direction/regime explicitly (this is likely to reveal fixed-time-barrier bias, see §5.2).
- This must be evaluated as an actual experiment, not assumed correct: train both the exclusion approach and a sample-weighted alternative (down-weight `-2`/`-3` rather than drop/keep-as-loss) and walk-forward compare. Whichever produces better-calibrated (not just higher-WR) live-simulated buckets wins.

### 5.2 Time barrier: consider direction-asymmetric horizons

Given XAUUSD's documented tendency to trend down faster than it grinds up ("stairs up, elevator down"), a single fixed 60-bar horizon likely disadvantages BUY setups specifically (more timeouts/SOTW). **Action item, not yet decided:** pull the timeout/SOTW rate split by direction (data now exists from the v3.0 diagnostic work) and test whether a longer horizon for BUY (e.g., 90 bars) closes the gap without degrading SELL.

### 5.3 Per-direction, not just per-model, evaluation discipline

Every labeling and validation change must report BUY and SELL metrics **separately**, never pooled — pooling was directly responsible for the inverse-calibration finding on SELL going unnoticed for as long as it did.

---

## 6. Risk & Execution Layer

- **Position Sizing & Risk Modes** (Current baseline: $10 fixed risk, e.g., 0.02–0.03 lot):
  - Lot size formula: $\text{Lot Size} = \text{max}\left(0.01, \text{min}\left(0.10, \text{round}\left(\frac{\text{Target Risk USD}}{\text{SL Pips} \times 10.0}, 2\right)\right)\right)$.
  - **Planned Risk Modes (`core/config.py`):**
    - `MINIMUM`: Hardcoded `0.01` micro-lot for live real-money testing (zero-stress micro risk).
    - `FIXED_DOLLAR` *(Current)*: Hardcoded `$10.00` fixed dollar risk per trade ($0.04\%$ equity on \$24.8k, $1.0\%$ on \$1k).
    - `PCT_EQUITY`: Fixed percentage equity risk per trade ($0.5\% - 1.0\%$).
  - Martingale explicitly banned at the architecture level (no lot-scaling-on-loss code path exists anywhere in the system).
- **Dynamic ATR & Swing-based SL/TP**, replacing static 40/60 pip targets:
  - `SL = max(15, min(90, max(k_sl × ATR, Swing_Boundary_Offset)))` (Removed 30-pip floor to allow small scalp trades).
  - `TP = round(SL * 1.5)` (Strict 1:1.5 RR, no overrides).
  - Uses `get_swing_levels()` (lookback=20) to place SL 2 pips beyond recent Swing High/Low boundaries.
  - **ATR cold-start guard (Aug 10 fix):** ATR fallback changed from `0.0` to `1.5` with a hard floor of `0.5`. Trades are skipped when `ATR < 0.5` to prevent 0-pip SL/TP after restarts.
  - Directly addresses the v3.0 failure mode: fixed 60-pip TP too far in low vol (timeout decay), fixed 40-pip SL too tight in high vol (Fast SOTW).
- **Session throttle (22:00 WIB Hard Cutoff)**: All sessions after 22:00 WIB marked `CLOSED` — no trading. 15-minute cooldown at NY Overlap open (19:00–19:15 WIB) to avoid session-transition fakeouts.
- **News embargo**: unchanged from v3.0 (30m pre / 60m post high-impact ForexFactory events). `Holiday` impact events are deliberately ignored to prevent freezing the bot during low-volume sessions; the bot relies on its internal volatility features (`atr`, `tick_volume`) to handle slow markets natively.
- **Regime gate (H1 Trend Filter)**: Uses a data-backed asymmetric "Dead Zone" based on ATR-normalized `rel_h1` distance:
  - **SELL Danger Zone:** `1.5 < rel_h1 < 9.0` (Blocks shorting into a strong, unexhausted pump).
  - **BUY Danger Zone:** `rel_h1 < -9.5` (Blocks catching a deep falling knife).

---

## 7. Model Architecture

- **Two independent LightGBM binary classifiers** (BUY / SELL) — retained. Rationale unchanged from original design docs: asymmetric market dynamics, independent thresholds, ambiguous-signal handling via "both high confidence → stay flat."
- **Class imbalance handling:** Currently `scale_pos_weight=1.0` (effectively disabled). *(Note: PRD originally specified `is_unbalance=True` or explicit weight. The `1.0` setting was found to perform adequately with the current dataset. Re-evaluate when dataset grows past 20k rows.)*
- **Regularization:** `n_estimators=50`, `learning_rate=0.03`, `max_depth=3`, `min_child_samples=50`. *(Note: `num_leaves` and `lambda_l1/l2` are not yet tuned — deferred to Phase 2 hyperparameter search.)*
- **Post-hoc probability calibration layer: Isotonic Regression + 5-Fold TimeSeriesSplit Out-Of-Fold (OOF)**, fit separately per direction, sitting between raw LightGBM output and the live threshold check. This is a direct, structural response to the discovered inverse-calibration finding on SELL and the flat/capped curve on BUY — rather than trusting raw `predict_proba` output as tradeable confidence, it gets recalibrated against actual realized outcomes before being thresholded. (Updated Aug 11: Switched from random KFold to TimeSeriesSplit to fix chronological data leakage during OOF generation).
  - **Calibrator verdict (Aug 10, 2026):** Platt scaling was tested in a parallel codebase (`ai-trading`) and **rejected**. LightGBM `max_depth=3` outputs cluster in a narrow band (~0.35–0.50). Platt fits a sigmoid through this cluster → flat zone → BUY slope collapsed to 0.0 (completely dead). Isotonic's non-parametric step function captures the lumpy miscalibration correctly. Live result: Isotonic +$76 (5/5 wins) vs Platt -$100 (consecutive losses) on the same market day.
  - Per-session calibrators (`calibrator_london`, `calibrator_ny`, `calibrator_asia`) are architecturally supported but currently **disabled** (`session_calibrators = {}`) due to insufficient per-session sample size. Re-enable at N>500 trades per session.
- **Session-transition features feed both models** (not a separate third model yet — see §9 for the deferred regime-classifier idea). Liquidity-sweep features (`swept_session_high/low`) are deferred to Phase 2.

---

## 8. Validation & Experimentation Discipline

1. **Walk-forward validation:** ✅ **Implemented for Calibration.** The probability calibrator uses 5-Fold `TimeSeriesSplit` to generate Out-Of-Fold predictions, ensuring it never uses future data to predict past folds. The final holdout evaluation still uses a static 80/20 chronological split with a 120-bar embargo gap (line 140–142 of `ml_lightgbm.py`).
2. **Champion/challenger deployment (PLANNED — not yet implemented):** Target is shadow mode for new models before promotion. Currently, retrained models go live directly after manual review.
3. **Calibration-bucket reporting is now a standard, automated part of every model evaluation** (not a one-off diagnostic) — win rate by probability decile, by direction, both on historical and live-shadow data, checked for monotonicity and confidence intervals (not just point estimates — the earlier report over-trusted small-n buckets like n=76).
4. **Model version logging**: ✅ every row in the live prediction/outcome table includes the exact model artifact hash. This closes the "was live and historical evaluation even using the same model" gap that couldn't be ruled out in the v3.0 postmortem.
5. **Hyperparameter and threshold search** (`h1_threshold`, probability cutoff, `k_sl`/`k_tp`) via grid or Bayesian search against the walk-forward harness, not hand-tuned during live debugging.
6. **Feature-level pre-registration**: before any new feature (especially structural/SMC ones) is added to the training set, log its liveness rate and, where applicable, a visual spot-check against charts — this check is now a checklist item in the PR/commit process, not an afterthought.

---

## 9. Phased Roadmap

**Phase 1 (this rebuild):**
Fix label collapsing, feature mislabeling/sentinel issues, add dynamic ATR-based SL/TP, walk-forward validation, per-direction calibration layer, session-transition + liquidity-sweep features, model-version logging, class-imbalance handling. Ship as MIA v4.0.

**Phase 2 (after v4.0 is stable in shadow mode for a full validation cycle):**
- Proper swing-based OTE/OB reintroduction, if the sweep feature proves out and there's appetite for more SMC surface area.
- BOS/CHOCH genuine structure-sequence detection.
- Direction-asymmetric time barriers if §5.2 investigation supports it.
- **Equity-based position sizing (1% risk):** Replace fixed $10 risk with `0.01 × account_equity`. Requires EA to send `AccountInfoDouble(ACCOUNT_EQUITY)` in ZMQ JSON payload. Current fixed $10 is ~1% on $1,000 but won't scale as equity grows.

**Phase 3 (exploratory, not committed):**
- Regime classifier as an explicit gating model ahead of BUY/SELL inference (the four-model architecture proposed in external review) — only worth pursuing once the two-model system's calibration is proven stable, given the data-starvation risk of further conditioning an already-thin trade sample.
- Tick-level order-flow proxies if a suitable data source becomes available.

---

## 10. Monitoring & Retraining (Live Operations)

> **Implementation status:** Retrain is manual. Drift monitoring and escalation ladder are **PLANNED but not yet implemented.**

- **Retrain cadence**: weekly/bi-weekly rolling-window retrain, each validated through the full walk-forward harness before challenger promotion.
- **Drift monitoring (PLANNED)**, three layers:
  - *Feature drift*: rolling PSI per feature vs. training distribution.
  - *Prediction drift*: rolling distribution of output probabilities per direction (catches indecisive-clustering before P&L shows it).
  - *Performance/concept drift*: rolling realized win rate and expectancy per direction vs. a statistically-bounded control band (not eyeballed).
- **Escalation ladder** on drift trigger: reduce size → halt new entries (open positions manage out) → full stop + forced re-validation, in that order, never a single-step kill switch.
- **Full audit logging retained and extended**: ✅ every prediction, full feature vector, realized outcome, and model version — this is what made the entire diagnostic process in this document possible, and it stays non-negotiable.

---

## 11. Open Questions (explicitly unresolved, need investigation before Phase 1 is "done")

1. Does a direction-asymmetric time barrier close the BUY/SELL timeout gap, or is a fixed horizon fine once SOTW-handling is fixed?
2. Are the BUY and SELL feature/execution code paths verified symmetric (spread handling, FVG detection mirroring, etc.) — this audit was recommended but not yet completed as of this document.
3. Was the SELL inverse historical calibration finding ever explained (model-version mismatch? regime-specific? sample artifact?) — flagged as high-priority, unresolved.
4. What does XAUUSD's actual price/`macro_bias` distribution look like over the specific live-trading window that produced the 11.7% BUY WR — needed to confirm or refute the regime-drift narrative directly rather than inferring it.

---

## 12. LLM Integration (Supplementary, Not Core Inference)

LightGBM remains the sole live decision-making model. LLMs are deliberately kept **out of the hot path** (ZMQ tick/candle loop) and are used only where their strengths — unstructured text understanding, slow-cadence reasoning, natural-language summarization — apply. Every LLM output that touches the trading system does so as a logged, versioned *feature* or *alert*, never as a direct trade trigger.

### 12.1 Where an LLM fits

| Use case | Cadence | Integration point | Output |
|---|---|---|---|
| **News/event feature extraction** | Event-driven (on new ForexFactory release / scheduled macro print) | New async service, writes to feature store | `hawkish_dovish_score`, `surprise_magnitude`, `headline_sentiment` — structured, numeric/categorical, joined into the existing feature table like `macro_bias` |
| **Trade post-mortem / diagnostic assistant** | Batch (daily/weekly) | Offline, reads from the audit DB (features + labels + outcomes) | Natural-language cluster summaries of losing trades (e.g., regime/feature co-occurrence patterns) — research aid, not a pipeline component |
| **Regime/narrative context feature** | Slow (hourly/daily) | Feature store, alongside `macro_bias` | Categorical feature (e.g., "risk-off," "gold safe-haven bid") derived from recent financial news summaries — speculative, must be walk-forward tested like any other new feature before trusting it |
| **Development/ops copilot** | N/A (build-time, not runtime) | Outside the trading system entirely | Assists writing feature code, the walk-forward harness, and PR review — highest-value, lowest-risk use case since it never touches live decisions |
| **Drift-monitor alert summarization** | Triggered by existing drift monitor (§10) | Sits downstream of the rule-based escalation ladder | Human-readable explanation of a drift alert — communication layer only, does not itself gate or trigger the escalation actions |

### 12.2 Explicit non-fits (why LLMs are excluded from these)

- **Per-tick/per-candle direction prediction**: LLM inference latency is orders of magnitude too slow for M1 scalping, and LLMs are not calibrated numeric probability estimators the way a tuned LightGBM classifier is.
- **Triple Barrier labeling or technical feature computation**: these must be deterministic and exactly reproducible bar-by-bar for backtesting; LLM calls are neither fast nor guaranteed deterministic.
- **Direct trade execution decisions**: no LLM output is ever allowed to trigger a buy/sell without passing through the same deterministic Regime Gate, Calibration Layer, and Risk Engine (§3, §6, §7) as every other feature — hallucination risk in a live-money system is unacceptable without a bounded, auditable filter around it.

### 12.3 Implementation notes

- The news-sentiment service runs independently of the ZMQ hot loop and writes into the same feature store the Feature Engine already reads from — architecturally identical to how `macro_bias` is currently produced, just with an LLM-based producer instead of a price-slope calculation.
- All LLM-derived features are subject to the same feature pre-registration discipline as everything else in this PRD (§8, item 6): liveness-rate check, and walk-forward validated for actual predictive lift before being trusted in the live model — an LLM-derived feature is not exempt from proving itself just because it's novel.
- Every LLM call (prompt, model/version, raw output, parsed structured output) is logged in the audit DB alongside the resulting feature value, for the same reproducibility/debuggability reasons the rest of this system is logged so thoroughly.

---

## Appendix: Minimum Schema Additions Needed for v4.0

```
signals / snapshots table additions:
  - model_version_hash (text, not null)
  - volatility_regime (enum: LOW/NORMAL/HIGH)
  - mins_to_session_transition (float)
  - has_fvg (bool), fvg_dist_atr (float, nullable)
  - swept_session_high (bool), swept_session_low (bool)
  - wick_body_ratio (float)
  - tick_velocity (float)
  - calibrated_prob_buy, calibrated_prob_sell (float, post-calibration-layer output, distinct from raw model output)
  - raw_label (int: +1/-1/0/-2/-3, retained pre-collapse for future re-analysis)

llm_features table (new, §12):
  - event_id / timestamp
  - source_type (enum: NEWS_RELEASE / NARRATIVE_SUMMARY)
  - llm_model_version (text, not null)
  - raw_prompt, raw_output (text, for audit/reproducibility)
  - hawkish_dovish_score, surprise_magnitude, headline_sentiment, narrative_regime (nullable, populated per source_type)
```
