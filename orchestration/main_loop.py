import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zmq
import json
import pandas as pd
import time
import datetime
from collections import deque
from data_engine.feature_builder import FeatureBuilder
from core.database import DatabaseManager
from intelligence.ml_lightgbm import LightGBMPredictor, MonotonicPlattScaler
import __main__
__main__.MonotonicPlattScaler = MonotonicPlattScaler
from core.config import FF_CALENDAR_URL

def main_loop(port=5557):
    # 1. Setup Konfigurasi
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://localhost:{port}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    # ponytail: publisher socket to send trades back to MT4
    pub_socket = context.socket(zmq.PUB)
    pub_socket.bind("tcp://*:5558")
    
    data_buffer = deque(maxlen=100)
    builder = FeatureBuilder()
    db = DatabaseManager()
    
    ml_model_buy = LightGBMPredictor(direction='buy')
    ml_model_sell = LightGBMPredictor(direction='sell')

    # Variabel untuk melacak candle & trade & calendar state
    last_candle_id = None 
    active_trade_ids = set()
    MAX_CONCURRENT_TRADES = 3
    last_trade_time = 0.0
    last_calendar_fetch_time = 0.0
    cached_red_events = []
    
    print("[*] Main Orchestrator: Sistem MIA v4.0 Siap (Candle-Based Mode).")
    
    while True:
        try:
            message = socket.recv_string()
            data = json.loads(message)
            
            # ponytail: intercept MT4 trade closing reports
            if data.get('action') == "TRADE_CLOSED" or data.get('type') == "trade_close":
                closed_id = data.get('trade_id')
                db.log_trade_close(
                    trade_id=closed_id,
                    exit_price=data.get('exit_price'),
                    profit=data.get('profit'),
                    duration=data.get('duration')
                )
                if closed_id in active_trade_ids:
                    active_trade_ids.remove(closed_id)
                print(f"[+] Trade {closed_id} CLOSED. Profit: {data.get('profit')}")
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
                'd1_open': data.get('d1_open'),
                'volume': data.get('volume', 1.0)
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
                
                # ponytail: cached ForexFactory news embargo check — fetch XML at most once per 30 minutes to prevent rate-limit blocks
                news_embargo = False
                try:
                    from datetime import datetime as dt
                    from zoneinfo import ZoneInfo
                    now = dt.now(ZoneInfo("UTC"))

                    if time.time() - last_calendar_fetch_time >= 1800:
                        import requests
                        import xml.etree.ElementTree as ET
                        resp = requests.get(FF_CALENDAR_URL, 
                                           headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                        if resp.status_code == 200:
                            root = ET.fromstring(resp.content)
                            new_events = []
                            for event in root.findall('.//event'):
                                impact = event.findtext('impact', '').strip()
                                country = event.findtext('country', '').strip()
                                if impact not in ('High', 'Medium', 'Holiday') or country not in ('USD', 'EUR', 'JPY', 'CNY', 'GBP'):
                                    continue
                                date_str = event.findtext('date', '').strip()
                                time_str = event.findtext('time', '').strip()
                                if not date_str or not time_str or time_str in ('Tentative', 'All Day'):
                                    continue
                                try:
                                    event_dt = dt.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
                                    event_dt = event_dt.replace(tzinfo=ZoneInfo("America/New_York"))
                                    title = event.findtext('title', 'Unknown')
                                    new_events.append((event_dt, title, impact))
                                except ValueError:
                                    continue
                            cached_red_events = new_events
                            last_calendar_fetch_time = time.time()
                            print(f"[*] ForexFactory Calendar updated cleanly: {len(cached_red_events)} events cached.")

                    for event_dt, title, impact in cached_red_events:
                        mins_diff = (event_dt - now).total_seconds() / 60.0
                        embargo_before, embargo_after = (-30, 60) if impact in ('High', 'Holiday') else (-15, 15)
                        
                        if embargo_before <= mins_diff <= embargo_after:
                            print(f"[!] {impact.upper()} IMPACT NEWS EMBARGO: {title} ({mins_diff:+.0f}min)")
                            news_embargo = True
                            break
                except Exception as e:
                    pass  # ponytail: if calendar fetch fails or rate limits, fallback to cached schedule without crashing

                if news_embargo:
                    print("[!] NEWS EMBARGO. Sitting on hands.")
                
                # Masukkan ke fitur agar tersimpan di DB
                features["macro_bias"] = macro_bias
                
                # ponytail: label trading session directly into JSON features for future ML
                # ponytail: exact WIB (UTC+7) session boundaries
                # ASIAN:   05:00 - 13:59 WIB
                # LONDON:  14:00 - 18:59 WIB
                # OVERLAP: 19:00 - 22:00 WIB (Hard cutoff at 22:00 WIB to stop late-night spread bleed)
                # CLOSED:  22:01 - 04:59 WIB (Off-hours / late night)
                from zoneinfo import ZoneInfo
                now_wib = datetime.datetime.now(ZoneInfo("Asia/Jakarta"))
                time_val = now_wib.hour + (now_wib.minute / 60.0)
                
                if 5.0 <= time_val < 14.0:
                    current_session = "ASIAN"
                elif 14.0 <= time_val < 19.0:
                    current_session = "LONDON"
                elif 19.0 <= time_val <= 22.0:
                    current_session = "OVERLAP"
                else:
                    current_session = "CLOSED"
                
                features["session"] = current_session

                # ML prediksi peluang (0% - 100%)
                # ponytail: route through per-session calibrator (middle-ground architecture)
                prob_buy, raw_buy = ml_model_buy.predict(features, session=current_session, return_raw=True)
                prob_sell, raw_sell = ml_model_sell.predict(features, session=current_session, return_raw=True)
                
                # Simpan probabilitas ke features agar tercatat di database (untuk audit nanti)
                features["live_prob_buy"] = prob_buy
                features["live_prob_sell"] = prob_sell
                
                # Get active model version hash for traceability
                active_hash = f"B:{ml_model_buy.get_model_version_hash()}|S:{ml_model_sell.get_model_version_hash()}"

                # Simpan ke DB
                db.save_snapshot(
                    symbol="XAUUSD", 
                    price=data.get('bid'), 
                    features=features,
                    label=None,
                    sell_label=None,
                    high=data.get('high'),
                    low=data.get('low'),
                    model_version_hash=active_hash
                )
                
                # ponytail: softened H1 trend filter. Only block when trend is strong (>0.15% from H1 close).
                h1_threshold = 0.0015
                if features.get('rel_h1', 0) < -h1_threshold:
                    prob_buy = 0.0
                elif features.get('rel_h1', 0) > h1_threshold:
                    prob_sell = 0.0

                print(f"[*] AI Win Prob -> BUY: {prob_buy * 100:.1f}% (Raw: {raw_buy * 100:.1f}%) | SELL: {prob_sell * 100:.1f}% (Raw: {raw_sell * 100:.1f}%) | Dist EMA: {features['dist_ema_50']:.4f}")

                # Only trade if we are in high priority sessions
                tradeable_sessions = ["ASIAN", "LONDON", "OVERLAP"]
                
                # ponytail: 15-minute NY Overlap Open Cooldown (19:00-19:15 WIB)
                # Pauses entries at NY open to avoid choppy session transition fakeouts
                ny_cooldown = (current_session == "OVERLAP" and time_val >= 19.0 and time_val < 19.25)
                if ny_cooldown and max(prob_buy, prob_sell) >= 0.40:
                    print(f"[!] NY OVERLAP OPEN COOLDOWN (19:00-19:15 WIB): Pausing entry to avoid choppy session transition.")

                if (current_session in tradeable_sessions) and not news_embargo and not ny_cooldown:
                    # Pick the highest probability
                    best_prob = max(prob_buy, prob_sell)
                    best_dir = "BUY" if prob_buy >= prob_sell else "SELL"
                    
                    # ponytail: Direction-Asymmetric Thresholds (Platt Calibrated)
                    # BUY prior base rate ~35% (0.35 thresh = high confidence, 45.1% WR / +$1,680 P&L out-of-sample)
                    # SELL prior base rate ~42% (0.40 thresh = high confidence)
                    min_thresh = 0.35 if best_dir == "BUY" else 0.40
                    
                    # ponytail: prevent stacking duplicate trades — max 3 active trades, 3-min (180s) cooldown
                    time_since_trade = time.time() - last_trade_time
                    if best_prob >= min_thresh and len(active_trade_ids) < MAX_CONCURRENT_TRADES and time_since_trade >= 180:
                        trade_id = int(time.time())
                        active_trade_ids.add(trade_id)
                        last_trade_time = time.time()
                        
                        ask = data.get('ask', 0.0)
                        bid = data.get('bid', 0.0)
                        atr = features.get('atr', 1.5)
                        
                        # ponytail: Dynamic Per-Session ATR SL/TP Scaling
                        # ceiling: these multipliers are empirical from week 1 data, revisit at n=500+ trades per session
                        if current_session == "LONDON":
                            atr_sl_mult, atr_tp_mult = 1.3, 2.0
                        elif current_session == "OVERLAP":
                            atr_sl_mult, atr_tp_mult = 2.0, 3.0
                        else:  # ASIAN
                            atr_sl_mult, atr_tp_mult = 1.0, 1.5
                        
                        atr_sl_pips = round((atr * atr_sl_mult) * 10)
                        atr_tp_pips = round((atr * atr_tp_mult) * 10)
                        
                        if best_dir == "BUY":
                            swing_low = features.get('swing_low', ask - 4.0)
                            swing_sl_pips = round(abs(ask - (swing_low - 0.20)) * 10)
                            sl_pips = max(15, min(90, max(swing_sl_pips, atr_sl_pips)))
                            chosen_hash = ml_model_buy.get_model_version_hash()
                        else:
                            swing_high = features.get('swing_high', bid + 4.0)
                            swing_sl_pips = round(abs((swing_high + 0.20) - bid) * 10)
                            sl_pips = max(15, min(90, max(swing_sl_pips, atr_sl_pips)))
                            chosen_hash = ml_model_sell.get_model_version_hash()
                            
                        tp_pips = round(sl_pips * 1.5)
                        
                        # Dynamic Position Sizing ($10 fixed dollar risk target)
                        target_risk_usd = 10.0
                        calculated_lot = round(target_risk_usd / (sl_pips * 10.0), 2)
                        dynamic_lot = max(0.01, min(0.10, calculated_lot))
                        
                        order_msg = {
                            "action": best_dir,
                            "trade_id": trade_id,
                            "symbol": "XAUUSD",
                            "lot": dynamic_lot,
                            "sl_pips": sl_pips,
                            "tp_pips": tp_pips
                        }
                        pub_socket.send_string(json.dumps(order_msg))
                        
                        entry_price = ask if best_dir == "BUY" else bid
                        
                        db.log_trade_open(
                            trade_id=trade_id,
                            direction=best_dir,
                            entry_price=entry_price,
                            features=features,
                            macro_bias=macro_bias,
                            probability=best_prob,
                            model_version_hash=chosen_hash
                        )
                        
                        print(f"[+] Signal {best_dir} dikirim ke MT4! (TradeID: {trade_id} | Lot: {dynamic_lot} | SL: {sl_pips}p | TP: {tp_pips}p | ModelHash: {chosen_hash})")
                
                # Update ID candle agar tidak simpan berulang
                last_candle_id = current_candle_id
            
        except Exception as e:
            print(f"[!] Error Orchestrator: {e}")
            continue  # ponytail: don't kill the bot on a single error

if __name__ == "__main__":
    main_loop()