import requests
import json
import time
import xml.etree.ElementTree as ET
import sys
import os

# Add root to sys.path so we can import core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import OLLAMA_URL, OLLAMA_MODEL, LLM_TEMPERATURE, RSS_URL, MACRO_STATE_FILE

# ponytail: ForexFactory calendar RSS for red folder events
FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

def fetch_news():
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(RSS_URL, headers=headers, timeout=10)
        root = ET.fromstring(resp.content)
        # Ambil 5 judul berita terakhir dari standard RSS
        titles = [item.find('title').text for item in root.findall('.//item') if item.find('title') is not None][:5]
        return "\n".join(titles)
    except Exception as e:
        print(f"[!] Gagal fetch berita: {e}")
        return ""

def check_news_embargo():
    """ponytail: Check ForexFactory calendar for red folder events within 30 minutes."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(FF_CALENDAR_URL, headers=headers, timeout=10)
        root = ET.fromstring(resp.content)
        
        from datetime import datetime, timedelta
        import re
        now = datetime.utcnow()
        
        for event in root.findall('.//event'):
            impact = event.findtext('impact', '').strip()
            if impact not in ('High', 'Holiday'):
                continue
            
            # ponytail: parse the date and time from FF calendar
            date_str = event.findtext('date', '').strip()
            time_str = event.findtext('time', '').strip()
            
            if not date_str or not time_str or time_str == 'Tentative' or time_str == 'All Day':
                continue
                
            try:
                event_dt = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
                # ponytail: embargo window = 30 min before to 15 min after
                if -30 <= (event_dt - now).total_seconds() / 60 <= 15:
                    title = event.findtext('title', 'Unknown')
                    print(f"[!] RED FOLDER: {title} at {event_dt} UTC")
                    return True
            except ValueError:
                continue
                
    except Exception as e:
        print(f"[!] Calendar fetch failed: {e}")
    
    return False

def get_llm_bias(news_text):
    if not news_text:
        return "NEUTRAL"
        
    prompt = f"""
    You are a macro-economic trader. Based on the following news headlines about Gold (XAUUSD), 
    are we currently BULLISH, BEARISH, or NEUTRAL? 
    Reply ONLY with one word: BULLISH, BEARISH, or NEUTRAL.

    News:
    {news_text}
    """
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": LLM_TEMPERATURE
        }
    }
    
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        reply = resp.json().get("response", "").upper()
        
        if "BULLISH" in reply: return "BULLISH"
        if "BEARISH" in reply: return "BEARISH"
        return "NEUTRAL"
    except Exception as e:
        print(f"[!] Ollama error: {e}")
        return "NEUTRAL"

def run_agent():
    print("[*] Macro Agent: Membaca berita...")
    news = fetch_news()
    
    print("[*] Macro Agent: Checking calendar...")
    embargo = check_news_embargo()
    
    print("[*] Macro Agent: Berpikir...")
    bias = get_llm_bias(news)
    
    state = {
        "timestamp": time.time(),
        "bias": bias,
        "news_embargo": embargo  # ponytail: red folder brake
    }
    
    with open(MACRO_STATE_FILE, 'w') as f:
        json.dump(state, f)
        
    embargo_str = " [EMBARGO ACTIVE]" if embargo else ""
    print(f"[*] Macro Agent Selesai. Bias: {bias}{embargo_str}. Disimpan ke {MACRO_STATE_FILE}")

if __name__ == "__main__":
    while True:
        run_agent()
        print("[*] Sleeping for 15 minutes...")
        time.sleep(900)