import zmq
import json
import pandas as pd
from collections import deque
from data_engine.feature_builder import FeatureBuilder
from core.database import DatabaseManager

def main_loop(port=5555):
    # 1. Setup Konfigurasi
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://localhost:{port}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    data_buffer = deque(maxlen=100)
    builder = FeatureBuilder()
    db = DatabaseManager()
    
    # Variabel untuk melacak candle terakhir agar tidak duplikat
    last_candle_id = None 
    
    print("[*] Main Orchestrator: Sistem MIA v3.0 Siap (Candle-Based Mode).")
    
    while True:
        try:
            message = socket.recv_string()
            data = json.loads(message)
            
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
                'h1_close': data.get('h1_close'),
                'h4_close': data.get('h4_close')
            }
            
            if len(data_buffer) > 0 and data_buffer[-1].get('time') == current_candle_id:
                data_buffer[-1] = candle
            else:
                data_buffer.append(candle)
            
            # 3. Proses hanya jika ada candle baru dan buffer cukup
            if len(data_buffer) >= 3 and current_candle_id != last_candle_id:
                df = pd.DataFrame(data_buffer).drop_duplicates()
                features = builder.build(df)
                
                # Simpan ke DB
                db.save_snapshot(symbol="XAUUSD", price=data.get('bid'), features=features)
                
                print(f"[*] Snapshot tersimpan | Candle: {current_candle_id} | Near OB: {features['is_near_ob']}")
                
                # Update ID candle agar tidak simpan berulang
                last_candle_id = current_candle_id
            
        except Exception as e:
            print(f"[!] Error Orchestrator: {e}")
            break

if __name__ == "__main__":
    main_loop()