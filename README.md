# 🚀 MIA v3.0: Quantitative ML + LLM Trading System

## 📌 Philosophy
MIA v3.0 is built on the **Lazy Senior Dev (Ponytail) Principle**: "Build the minimum that works. No unrequested abstractions, no boilerplate." 

The system relies on strict **Separation of Concerns**:
- **ML is the Engine (Micro):** LightGBM handles high-frequency tick data, analyzing purely objective mathematical features (EMA, RSI, ATR) to predict win probability in 0.001 seconds.
- **LLM is the Steering Wheel (Macro):** DeepSeek-R1 runs asynchronously in the background, analyzing news headlines to determine the broader market bias (BULLISH/BEARISH/NEUTRAL). 

This split ensures the bot trades at maximum speed without getting blocked by LLM latency, while still protecting you from trading against massive fundamental shifts.

---

## 🛠️ The Tech Stack
* **Language:** Python 3.11+
* **Broker Bridge:** ZeroMQ (ZMQ) for sub-millisecond MT4 communication
* **Micro Intelligence:** `LightGBM` (Extremely fast tabular data predictor)
* **Macro Intelligence:** `DeepSeek-R1:8B` (via local Ollama)
* **Storage:** `SQLite` (JSON feature dumping)

---

## 📂 Project Architecture

```text
mia_v3/
├── core/                       
│   ├── config.py               # Centralized configuration (Ollama URLs, ML params)
│   ├── database.py             # SQLite data persistence
│
├── data_engine/                
│   ├── indicator_math.py       # Math logic (RSI, ATR, BB_BW, FVG). *SMC Noise Dropped.*
│   └── feature_builder.py      # Factory that converts raw ticks into a feature matrix
│
├── intelligence/               
│   ├── ml_lightgbm.py          # ML predictor. Drops garbage data, trains, predicts probability.
│   └── llm_macro_agents.py     # Asynchronous agent. Fetches RSS, gets LLM bias, saves to JSON.
│
├── orchestration/              
│   ├── main_loop.py            # The Gatekeeper. Listens to ZMQ, fetches Macro JSON, executes ML.
│
├── execution/                  
│   └── MIA_v3_ZMQ_Bridge.mq4   # MQL4 side ZMQ sender
│
└── export_csv.py               # Lazy utility to dump SQLite JSON into Excel-ready CSV
```

---

## 🗺️ The Start-to-Finish Master Plan

### Phase 1: Data Collection & Synchronization (Current Phase)
The ML engine is useless without clean data.
1. Run `main_loop.py` to collect live MT4 ticks via ZMQ.
2. Run `llm_macro_agents.py` on a 15-minute background cron job.
3. `main_loop.py` automatically injects the LLM's `macro_bias` into the technical feature snapshot and saves it to SQLite.

### Phase 2: ML Model Training
Once sufficient data is collected (e.g., after Monday's session):
1. Run `export_csv.py` to review the data.
2. Label the data using a Triple Barrier Method (Hit TP = 1, Hit SL = 0).
3. Run `ml_lightgbm.py` to train the model on the clean dataset.

### Phase 3: Live Execution
When the ML model achieves a >55% win probability on cross-validation:
1. Connect `risk_calculator.py` to `main_loop.py`.
2. Add the execution logic: 
   - `IF ml_probability > 75% AND ml_direction == macro_bias -> EXECUTE TRADE`
3. Send the trade signal back over ZMQ to MT4.

---
*Note: All SMC (Order Block) heuristic algorithms were audited and permanently removed due to zero predictive correlation. Do not re-add them.*