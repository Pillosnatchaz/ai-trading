# ==========================================
# MIA v3.0 - CENTRALIZED SETTINGS
# ==========================================

# 1. LLM MACRO AGENT SETTINGS
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "deepseek-r1:8b"
LLM_TEMPERATURE = 0.1 # Keep it low for trading (less hallucination)
# RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US"
RSS_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
MACRO_STATE_FILE = "macro_state.json"
LLM_INTERVAL_MINUTES = 15

# 2. LIGHTGBM ML SETTINGS
LGBM_ESTIMATORS = 100
LGBM_LEARNING_RATE = 0.05
LGBM_MAX_DEPTH = 5

# 3. SYSTEM SETTINGS
ZMQ_PORT = 5555
DB_FILENAME = "ai_data.db"
