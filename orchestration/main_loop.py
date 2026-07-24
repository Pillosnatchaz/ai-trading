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
                # ponytail: use old candles to warm up indicators, but don't save to DB or trade
                candle_age_seconds = time.time() - current_candle_id
                if candle_age_seconds > 120:
                    last_candle_id = current_candle_id
                    continue  # features already calculated above, indicators are warm

                # ponytail: candle-based macro_bias — no LLM, no RSS, no hallucinations
                ema_slope = features.get('ema_50_slope', 0)
                if ema_slope > 0.0001:
                    macro_bias = "BULLISH"
                elif ema_slope < -0.0001:
                    macro_bias = "BEARISH"
                else:
                    macro_bias = "NEUTRAL"
                
                # ponytail: inline embargo check — runs every tick, no blind spots
                news_embargo = False
                try:
                    import requests
                    import xml.etree.ElementTree as ET
                    from datetime import datetime as dt
                    from zoneinfo import ZoneInfo
                    resp = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.xml", 
                                       headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                    root = ET.fromstring(resp.content)
                    now = dt.now(ZoneInfo("UTC"))
                    for event in root.findall('.//event'):
                        impact = event.findtext('impact', '').strip()
                        if impact not in ('High', 'Holiday'):
                            continue
                        date_str = event.findtext('date', '').strip()
                        time_str = event.findtext('time', '').strip()
                        if not date_str or not time_str or time_str in ('Tentative', 'All Day'):
                            continue
                        try:
                            # ponytail: FF times are US Eastern — convert to UTC for comparison
                            event_dt = dt.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
                            event_dt = event_dt.replace(tzinfo=ZoneInfo("America/New_York"))
                            mins_diff = (event_dt - now).total_seconds() / 60
                            # ponytail: 30 min before to 60 min after
                            if -30 <= mins_diff <= 60:
                                title = event.findtext('title', 'Unknown')
                                print(f"[!] RED FOLDER: {title} ({mins_diff:+.0f}min)")
                                news_embargo = True
                                break
                        except ValueError:
                            continue
                except Exception:
                    pass  # ponytail: if calendar fetch fails, don't block trading
                
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
                
                # ponytail: softened H1 trend filter. Only block when trend is strong (>0.15% from H1 close).
                # Small counter-trend trades near H1 close are allowed (mean-reversion zone).
                h1_threshold = 0.0015
                if features.get('rel_h1', 0) < -h1_threshold:
                    prob_buy = 0.0
                elif features.get('rel_h1', 0) > h1_threshold:
                    prob_sell = 0.0

                # Only trade if we are in high priority sessions
                tradeable_sessions = ["LONDON", "OVERLAP"]
                
                if (current_session in tradeable_sessions) and not news_embargo:
                    # Pick the highest probability
                    best_prob = max(prob_buy, prob_sell)
                    best_dir = "BUY" if prob_buy >= prob_sell else "SELL"
                    
                    # ponytail: veteran 13k-row models restored. Do NOT retrain until Friday night (need 4000+ new OHLC rows).
                    if best_prob >= 0.45:
                        trade_id = int(time.time())
                        
                        order_msg = {
                            "action": best_dir,
                            "trade_id": trade_id,
                            "symbol": "XAUUSD",
                            "lot": 0.01,
                            "sl_pips": 40,
                            "tp_pips": 60
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