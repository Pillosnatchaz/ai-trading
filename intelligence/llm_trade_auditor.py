import requests
import json
import sqlite3
import os

class LLMTradeAuditor:
    """
    Ponytail: LLM Trade Diagnostician using local Ollama (DeepSeek / Llama3).
    Analyzes losing trades and logs concise root-cause post-mortems to DB.
    """
    def __init__(self, ollama_url="http://localhost:11434/api/generate", model="deepseek-r1:8b"):
        self.ollama_url = ollama_url
        self.model = model

    def diagnose_loss(self, trade_id, direction, entry_price, exit_price, features_json):
        """Sends trade data to Ollama and returns a concise 1-2 sentence loss diagnosis."""
        fdict = json.loads(features_json) if isinstance(features_json, str) else (features_json or {})
        
        rsi = fdict.get('rsi', 50.0)
        ema_slope = fdict.get('ema_50_slope', 0.0)
        atr = fdict.get('atr', 1.5)
        macro_bias = fdict.get('macro_bias', 'NEUTRAL')
        session = fdict.get('session', 'UNKNOWN')
        
        prompt = f"""You are an elite Forex risk auditor. A XAUUSD (Gold) scalp trade lost. Analyze the technical parameters and return a 1-sentence root cause diagnosis.

Trade Parameters:
- Direction: {direction}
- Entry: {entry_price} | Exit: {exit_price}
- Session: {session} | Macro Bias: {macro_bias}
- RSI (14): {rsi:.1f} | EMA 50 Slope: {ema_slope:.5f} | ATR: {atr:.2f}

Format your response as:
CATEGORY: [COUNTER_TREND_FAKEOUT | SPREAD_EXPANSION | NEWS_WHIPSAW | STRUCTURAL_DRIFT]
DIAGNOSIS: [1-sentence explanation of why the scalp failed]"""

        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False
            }
            resp = requests.post(self.ollama_url, json=payload, timeout=2)
            if resp.status_code == 200:
                result = resp.json().get('response', '').strip()
                return result
        except Exception:
            pass
            
        # Fallback if Ollama is offline or model still downloading
        return f"CATEGORY: STRUCTURAL_DRIFT\nDIAGNOSIS: Trade hit Stop Loss during {session} session under {macro_bias} bias (Ollama offline fallback)."

    def log_diagnosis_to_db(self, db_path, trade_id, diagnosis):
        """Stores diagnosis string into live_trades table if column exists."""
        try:
            conn = sqlite3.connect(db_path, timeout=10.0)
            cursor = conn.cursor()
            # Ensure column exists
            cursor.execute("PRAGMA table_info(live_trades)")
            cols = [c[1] for c in cursor.fetchall()]
            if 'ai_diagnosis' not in cols:
                cursor.execute("ALTER TABLE live_trades ADD COLUMN ai_diagnosis TEXT")
                
            cursor.execute("UPDATE live_trades SET ai_diagnosis = ? WHERE trade_id = ?", (diagnosis, int(trade_id)))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[!] Error logging AI diagnosis: {e}")

if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ai_data.db')
    auditor = LLMTradeAuditor()
    
    print("============================================================")
    print("TESTING LLM TRADE AUDITOR (POST-MORTEM LOSS DIAGNOSTIC)")
    print("============================================================")
    
    conn = sqlite3.connect(db_path, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT trade_id, direction, entry_price, exit_price, features_json 
        FROM live_trades 
        WHERE outcome = 'LOSS' 
        ORDER BY trade_id DESC LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    
    if row:
        t_id, direction, entry, exit_p, fjson = row
        print(f"[*] Auditing Latest Losing Trade #{t_id} ({direction} @ {entry} -> Exit: {exit_p})...")
        diag = auditor.diagnose_loss(t_id, direction, entry, exit_p, fjson)
        print("\n--- AI POST-MORTEM DIAGNOSIS ---")
        print(diag)
        auditor.log_diagnosis_to_db(db_path, t_id, diag)
        print("\n[+] Diagnosis logged to DB live_trades table!")
    else:
        print("[!] No losing trades found in database to test.")
