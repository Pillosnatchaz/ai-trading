# 🚀 MIA v4.0 — LightGBM XAUUSD Scalping System

An automated gold (XAUUSD) scalper on the M1 timeframe. MetaTrader 4 is the hands,
Python is the brain, ZeroMQ connects them. Two LightGBM models each answer one
question per closed 1-minute candle: *if I open this trade right now, what is the
chance it reaches take-profit before stop-loss?* Everything else in the system is a
filter wrapped around that number.

See `PRD.md` for the full spec and `trading_notes.md` for the running log of what
actually happened in the market and why each filter exists.

---

## 📌 Philosophy

Built on the **Lazy Senior Dev (Ponytail) Principle**: build the minimum that
works, no unrequested abstractions, no boilerplate. The whole live system is one
350-line file.

Two rules that were learned the expensive way:

1. **LightGBM is the only thing that decides trades.** LLMs are deliberately kept
   out of the hot path — v3.0 used DeepSeek-R1 for news-driven market bias and it
   hallucinated direction from irrelevant articles (a Canadian mining stock press
   release once produced a BULLISH signal). `macro_bias` is now derived from the
   EMA-50 slope. LLM use is limited to offline analysis; see PRD §12.
2. **When live results and backtest numbers disagree, suspect the replay pipeline
   before doubting a live-derived filter.** See "The August 13 leak" below.

---

## 🛠️ Tech Stack

| | |
|---|---|
| Language | Python 3.11+ |
| Broker bridge | ZeroMQ — EA publishes on **5567**, Python publishes orders on **5568** |
| Model | LightGBM, two binary classifiers (BUY / SELL) |
| Calibration | Isotonic Regression on out-of-fold predictions |
| Storage | SQLite (`ai_data.db`), features stored as JSON per row |

`pip install -r requirements.txt`

---

## ⚙️ How the live loop works

`orchestration/main_loop.py` — one pass per closed M1 candle:

```
MT4 EA  --ZMQ 5567-->  main_loop
   bid/ask, M1 OHLC, tick volume, and iClose(tf,1) for M5/M15/H1/H4
        │
        ├─ FeatureBuilder.build()   ~20 features (see below)
        ├─ macro_bias               EMA-50 slope sign
        ├─ news embargo             ForexFactory XML, cached 30 min.
        │                           High impact: 30 min before / 60 min after.
        │                           Medium: 15 / 15. Sends CLOSE_ALL if inside.
        ├─ session tag              from WIB (UTC+7) wall clock
        ├─ predict() x2             LightGBM raw probability -> Isotonic calibrator
        ├─ save_snapshot()          EVERY candle, with the model hash that produced it
        ├─ H1 dead zone             hard-zeros the probability in known-bad regimes
        ├─ circuit breaker          3 consecutive losses in a direction -> 30 min pause
        └─ if prob >= min_thresh and slot free and cooldown elapsed:
               SL from ATR/swing (clamped), TP = SL x 1.5, then --ZMQ 5568--> MT4
```

**Sessions (WIB / UTC+7)** — anything outside these does not trade:

| Session | Window |
|---|---|
| ASIAN | 05:00 – 14:00 |
| LONDON | 14:00 – 19:00 |
| OVERLAP | 19:00 – 22:00 |
| CLOSED | 22:00 – 05:00 |

A 15-minute cooldown at the NY overlap open (19:00–19:15) skips session-transition
fakeouts. The 22:00 hard cutoff exists because late-session trades bled money on
wide spreads — 88 signals fired after 22:00 on July 23 and the streak wiped half
that day's gains.

**H1 dead zone** — `rel_h1` is the distance from the last completed H1 close,
divided by ATR. Certain ranges reliably lose:

- SELL blocked when `1.5 < rel_h1 < 9.0` (shorting into a strong, unexhausted rally)
  or `rel_h1 > 22.5` (structural break)
- BUY blocked when `rel_h1 < -9.5` (catching a falling knife)

⚠️ **These thresholds are derived from live results and must not be re-tuned from
`historical_snapshots` statistics.** Pre-Aug-13 historical data claimed the blocked
BUY zone won 93.71% — that number *was* the leak.

---

## 📂 Repo layout

```text
ai-trading-iso/
├── core/
│   ├── config.py               # news URL, ports. NOTE: the LGBM_* values here are
│   │                           #   stale — ml_lightgbm.py hardcodes its own.
│   └── database.py             # SQLite: snapshots + live_trades
│
├── data_engine/
│   ├── indicator_math.py       # RSI, ATR, Bollinger, Stochastic, EMA, FVG, swings
│   ├── feature_builder.py      # OHLC window -> feature dict. Used by BOTH live and replay.
│   ├── triple_barrier.py       # 5-class labeller (+1/-1/0/-2/-3), pessimistic OHLC
│   └── run_labeler.py          # applies the labeller across a DB table
│
├── intelligence/
│   ├── ml_lightgbm.py          # train / calibrate / predict, per direction
│   └── llm_*.py                # OFFLINE analysis only, never in the trade path
│
├── orchestration/
│   └── main_loop.py            # the whole live system
│
├── scripts/
│   ├── DumpHistory.mq4         # attach to an M1 chart -> history_dump.csv
│   └── build_historical_db.py  # replays that CSV through FeatureBuilder
│
├── MIA_v3_ZMQ_Bridge_Dual.mq4  # EA for the demo account
├── MIA_v4_ZMQ_Bridge_Cent.mq4  # EA for the cent live account (see below)
└── test_live_config.py         # asserts the label/execution contract still holds
```

---

## 🏷️ Labelling and training

Labels come from the **Triple Barrier** method: from each bar, look forward up to 60
bars and record which happened first — take-profit, stop-loss, or neither.

Currently **40 pips SL / 60 pips TP / 60 bars**, where a pip is 0.1 in price. When a
single candle's range breaches both barriers, the stop is assumed to have hit first
(pessimistic). Five outcomes are recorded:

| label | meaning | used in training |
|---|---|---|
| `+1` | hit TP first | **win (1)** |
| `-1` | hit SL first | loss (0) |
| `0` | neither within 60 bars (timeout) | loss (0) |
| `-2` | hit SL, then TP within 15 bars ("fast" stop-out-then-win) | **excluded** — noise |
| `-3` | hit SL, then TP after 15 bars | loss (0) |

`-2` is dropped rather than counted as a loss: those setups were directionally
right and punishing them teaches the model to avoid good entries.

Raw LightGBM output is then **calibrated**. Raw scores cluster in a narrow band and
don't correspond to real win rates, so an Isotonic Regression maps them onto
observed outcomes using out-of-fold predictions from a 5-fold `TimeSeriesSplit`,
with a 60-row purge at each fold boundary (labels look 60 bars forward, so boundary
rows would otherwise be decided by prices inside the validation window). After
calibration, "0.52" genuinely means about 52%.

Platt scaling was tried and **rejected** — it fits a sigmoid through the narrow
cluster, flattens it, and collapsed the BUY slope to zero.

### ⚠️ Train on `historical_snapshots`, not `snapshots`

`ml_lightgbm.py` defaults to `table_name='snapshots'`, which is the **live** log the
bot appends to as it runs. The models are trained on `historical_snapshots`, the
bulk replay of the MT4 history dump. Accepting the default silently trains on the
wrong table.

```bash
# 1. Attach scripts/DumpHistory.mq4 to an M1 XAUUSD chart, copy the CSV here.
#    First raise Tools > Options > Charts > "Max bars in history/chart" — the
#    default of 65,000 silently caps the dump regardless of the script's input.
python scripts/build_historical_db.py                        # self-check, wipe, replay
python -m data_engine.run_labeler --table historical_snapshots
python -m intelligence.ml_lightgbm --table historical_snapshots
python test_live_config.py
```

`build_historical_db.py` **replaces** the table on each run, it does not append.

---

## 🩸 The August 13 leak (read before trusting any backtest)

`build_historical_db.py` built its higher-timeframe references with
`resample('1h').last().ffill()`. That places an hour's **final** close at the
**start** of that hour, and forward-fill then handed that price to every bar inside
it — so a bar at 13:01 was told what price would be at 13:59. Live, the EA sends
`iClose(tf, 1)`, the previous *completed* candle.

The model's two most important features therefore meant **opposite things** in
training and in production. It learned "buy the dip" from dips measured against the
future; live, that same reading means the market is falling, so it bought into every
drop. That is the 11.7% BUY win rate.

- Correlation of `rel_h1` with the next 30 minutes' return: **−0.672 → 0.004** after
  the fix (`.shift(1)`, guarded by `_selfcheck()` on every rebuild).
- Training accuracy fell **82% → 58%**. The drop *is* the success condition — the
  82% was the model grading its own homework with the answer key.
- Calibration became monotone in both directions for the first time.
- Peak confidence fell from 0.996 to ~0.55, and trade frequency dropped roughly 10x.

**Any feature derived from a resampled higher timeframe must be checked for ~zero
correlation with forward returns before it is trusted.** That check is what found
this, and it is mandatory after every rebuild.

Absolute prices (`swing_high`/`swing_low`) were also removed from the training
matrix on the same day — they are raw gold prices, so 98–100% of live values fall
outside the range the model ever saw. They remain in the feature dict for stop
placement.

---

## 💵 Risk and execution

- **Stop loss** from the wider of an ATR multiple and a recent swing boundary, then
  clamped. **Take profit is always SL × 1.5.**
- The 1:1.5 ratio makes mathematical breakeven **40%**, which is what the probability
  threshold is chosen against. Changing the ratio without relabelling invalidates
  the threshold.
- Position sizing, concurrent-trade limit and a 180-second cooldown between entries.
- **Martingale is banned at the architecture level** — no lot-scaling-on-loss code
  path exists anywhere.
- Circuit breaker: 3 consecutive losses in one direction pauses *that direction* for
  30 minutes; resets on any win.

`test_live_config.py` pins the contract between the four files that have to agree —
the labeller's SL/TP, the live clamp, the calibration purge width, and the EA's pip
size. It exists because on July 17 a model trained on 20/40 was executing 40/60 and
went 0 for 13.

---

## 🧪 Cent live test (branch `v4-live-test`)

Running on a small real-money HFM **Cent** account. A cent account's contracts are
1/100 of standard, which is the only way a minimum 0.01 lot produces a sane risk on
a very small balance — on a standard-lot account the smallest trade allowed would
risk most of it.

| setting | demo | cent live test |
|---|---|---|
| `min_thresh` | 0.42 | **0.50** |
| `MAX_CONCURRENT_TRADES` | 3 | **1** |
| lot | `$10 / (sl × 10)` | **fixed 0.01** |
| SL clamp | 15–90 pips | **30–60 pips** |

The clamp was narrowed because every label was computed at exactly 40 SL — an SL of
15 or 90 asks the model a question it was never trained on.

`MIA_v4_ZMQ_Bridge_Cent.mq4` differs from the demo EA in three ways: it defines a
pip as a literal `0.1` instead of `10 * Point` (on a 3-digit gold feed `Point`
becomes 0.001 and every stop would land **10× too tight**), it hard-caps lot size as
a live-money guard, and it prints the feed's digits and contract specs on attach so
that assumption is verified rather than hoped for.

⚠️ `min_thresh = 0.50` is **provisional** — it was measured against the current
calibrator. Retraining moves the isotonic steps and the number stops meaning
anything until it is recomputed.

---

## 📊 Status

**Working:** ZMQ bridge, dual model + isotonic calibration, triple-barrier
labelling, news embargo, session gating, H1 dead zone, dynamic SL/TP, circuit
breaker, full audit logging with model-version hashes on every row.

**Open:**

- BUY has never been convincingly shown to work. On the current holdout it is 50%
  at threshold 0.50, but n=118 and the confidence interval runs down to 41% —
  against a 40% breakeven that is not an answer. SELL is the stronger side.
- Walk-forward validation covers the *calibrator* only; the final holdout is still
  a static 80/20 chronological split. PRD §2 bans single-split validation, so this
  is a known gap pending more data.
- The `spread` feature is inert. The MT4 history dump contains no bid/ask, so
  `build_historical_db.py` fakes a constant 0.3 — a constant cannot be split on, so
  the model ignores it. Real spread only exists in the live `snapshots` table.
- Drift monitoring, champion/challenger shadow deployment and automated retraining
  are specified in PRD §10 but **not implemented**. Retraining is manual.
- Low-impact FOMC speakers are not embargoed (only High and Medium).
