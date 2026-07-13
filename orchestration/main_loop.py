import zmq
import json
import pandas as pd
import time
import datetime
from collections import deque
from data_engine.feature_builder import FeatureBuilder
from core.database import DatabaseManager
from intelligence.ml_lightgbm import LightGBMPredictor

def main_loop(port=5557):
    # 1. Setup Konfigurasi
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://localhost:{port}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    # ponytail: publisher socket to send trades back to MT5
    pub_socket = context.socket(zmq.PUB)
    pub_socket.bind("tcp://*:5558")
    
    data_buffer = deque(maxlen=100)
    builder = FeatureBuilder()
    db = DatabaseManager()
    
    ml_model_buy = LightGBMPredictor(direction='buy')
    ml_model_sell = LightGBMPredictor(direction='sell')

    # Variabel untuk melacak candle terakhir agar tidak duplikat
    last_candle_id = None 
    
    print("[*] Main Orchestrator: Sistem MIA v3.0 Siap (Candle-Based Mode).")
    
    while True:
        try:
            message = socket.recv_string()
            data = json.loads(message)
            
            # ponytail: intercept MT5 trade closing reports
            if data.get('action') == "TRADE_CLOSED":
                db.log_trade_close(
                    trade_id=data.get('trade_id'),
                    exit_price=data.get('exit_price'),
                    profit=data.get('profit'),
                    duration=data.get('duration')
                )
                print(f"[+] Trade {data.get('trade_id')} CLOSED. Profit: {data.get('profit')}")
                continue
            
            # 2. Ambil ID unik candle (misal: timestamp M1)
            # Pastikan EA mengirim field 'time'
            current_candle_id = data.get('time') 
            
            candle = {
                'time': current_candle_id,
                'bid': data.get('bid'),
                'ask': data.get('ask'),
                'open': data.get('open'),
                'high': data.get('high'),
                'low': data.get('low'),
                'close': data.get('close'),
                'm5_close': data.get('m5_close'),
                'm15_close': data.get('m15_close'),
                'h1_close': data.get('h1_close'),
                'h4_close': data.get('h4_close'),
                'd1_open': data.get('d1_open')
            }
            
            if len(data_buffer) > 0 and data_buffer[-1].get('time') == current_candle_id:
                data_buffer[-1] = candle
            else:
                data_buffer.append(candle)
            
            # 3. Proses hanya jika ada candle baru dan buffer cukup
            if len(data_buffer) >= 3 and current_candle_id != last_candle_id:
                df = pd.DataFrame(data_buffer).drop_duplicates()
                features = builder.build(df)

                # 4. Filter Old Candles (Historical Buffer)
                # MT4 sends 100 old candles on startup to build indicators. We should NOT save or trade them.
                candle_age_seconds = time.time() - current_candle_id
                if candle_age_seconds > 120:
                    last_candle_id = current_candle_id
                    continue

                # Baca Macro State (LLM)
                macro_bias = "NEUTRAL"
                news_embargo = False
                try:
                    # ponytail: stale data protection — if macro_state.json is older than 60 min, force NEUTRAL
                    import os
                    state_file = "macro_state.json"
                    if os.path.exists(state_file):
                        file_age_min = (time.time() - os.path.getmtime(state_file)) / 60
                        with open(state_file, "r") as f:
                            macro_state = json.load(f)
                        if file_age_min < 60:
                            macro_bias = macro_state.get("bias", "NEUTRAL")
                            news_embargo = macro_state.get("news_embargo", False)
                        else:
                            print(f"[!] macro_state.json is {file_age_min:.0f}min old. Forcing NEUTRAL.")
                except Exception:
                    pass
                
                # ponytail: news embargo — skip trading during Red Folder events
                if news_embargo:
                    print("[!] RED FOLDER NEWS EMBARGO. Sitting on hands.")
                
                # Masukkan ke fitur agar tersimpan di DB
                features["macro_bias"] = macro_bias
                
                # ponytail: label trading session directly into JSON features for future ML
                now = datetime.datetime.now() # Assuming server is UTC+7 (WIB)
                time_val = now.hour + (now.minute / 60.0)
                
                if 14.0 <= time_val < 19.5:
                    current_session = "LONDON"
                elif 19.5 <= time_val <= 23.0:
                    current_session = "OVERLAP"
                else:
                    current_session = "ASIAN"
                
                features["session"] = current_session

                # ML prediksi peluang (0% - 100%)
                prob_buy = ml_model_buy.predict(features)
                prob_sell = ml_model_sell.predict(features)
                
                # Simpan probabilitas ke features agar tercatat di database (untuk audit nanti)
                features["live_prob_buy"] = prob_buy
                features["live_prob_sell"] = prob_sell
                
                # Simpan ke DB
                db.save_snapshot(
                    symbol="XAUUSD", 
                    price=data.get('bid'), 
                    features=features,
                    label=None,
                    sell_label=None,
                    high=data.get('high'),
                    low=data.get('low')
                )
                
                print(f"[*] AI Win Probability -> BUY: {prob_buy * 100:.1f}% | SELL: {prob_sell * 100:.1f}% | Dist EMA: {features['dist_ema_50']:.4f}")
                
                # ponytail: EMERGENCY TREND FILTER. Don't fight H1 trend.
                if features.get('rel_h1', 0) < 0:
                    prob_buy = 0.0
                elif features.get('rel_h1', 0) > 0:
                    prob_sell = 0.0

                # Only trade if we are in high priority sessions
                tradeable_sessions = ["LONDON", "OVERLAP"]
                
                if (current_session in tradeable_sessions) and not news_embargo:
                    # Pick the highest probability
                    best_prob = max(prob_buy, prob_sell)
                    best_dir = "BUY" if prob_buy >= prob_sell else "SELL"
                    
                    # ponytail: A 45% probability from an AI trained on a 35% win rate is an incredibly strong signal.
                    if best_prob >= 0.45:
                        trade_id = int(time.time())
                        
                        order_msg = {
                            "action": best_dir,
                            "trade_id": trade_id,
                            "symbol": "XAUUSD",
                            "lot": 0.01,
                            "sl_pips": 30,
                            "tp_pips": 45
                        }
                        pub_socket.send_string(json.dumps(order_msg))
                        
                        entry_price = data.get('ask') if best_dir == "BUY" else data.get('bid') # Just for logging
                        
                        db.log_trade_open(
                            trade_id=trade_id,
                            direction=best_dir,
                            entry_price=entry_price,
                            features=features,
                            macro_bias=macro_bias,
                            probability=best_prob
                        )
                        
                        print(f"[+] Signal {best_dir} dikirim ke MT5! (TradeID: {trade_id})")
                
                # Update ID candle agar tidak simpan berulang
                last_candle_id = current_candle_id
            
        except Exception as e:
            print(f"[!] Error Orchestrator: {e}")
            continue  # ponytail: don't kill the bot on a single error

if __name__ == "__main__":
    main_loop()