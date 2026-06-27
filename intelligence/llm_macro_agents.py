import requests
import json
import time
import xml.etree.ElementTree as ET
import sys
import os

# Add root to sys.path so we can import core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import OLLAMA_URL, OLLAMA_MODEL, LLM_TEMPERATURE, RSS_URL, MACRO_STATE_FILE

def fetch_news():
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(RSS_URL, headers=headers, timeout=10)
        root = ET.fromstring(resp.content)
        # Ambil 5 judul berita terakhir
        titles = [item.find('title').text for item in root.findall('.//item')][:5]
        return "\n".join(titles)
    except Exception as e:
        print(f"[!] Gagal fetch berita: {e}")
        return ""

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
    
    print("[*] Macro Agent: Berpikir...")
    bias = get_llm_bias(news)
    
    state = {
        "timestamp": time.time(),
        "bias": bias
    }
    
    with open(MACRO_STATE_FILE, 'w') as f:
        json.dump(state, f)
        
    print(f"[*] Macro Agent Selesai. Bias: {bias}. Disimpan ke {MACRO_STATE_FILE}")

if __name__ == "__main__":
    run_agent()