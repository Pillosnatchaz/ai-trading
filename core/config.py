# ==========================================
# MIA v3.0 - CENTRALIZED SETTINGS
# ==========================================

# 1. LLM MACRO AGENT SETTINGS
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "deepseek-r1:8b"
LLM_TEMPERATURE = 0.1 # Keep it low for trading (less hallucination)
RSS_URL = "https://www.forexlive.com/feed"
# RSS_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
MACRO_STATE_FILE = "macro_state.json"
LLM_INTERVAL_MINUTES = 40

# 2. LIGHTGBM ML SETTINGS
# ponytail: severely restricted to prevent overfitting on tiny datasets
LGBM_ESTIMATORS = 20
LGBM_LEARNING_RATE = 0.05
LGBM_MAX_DEPTH = 3

# 3. SYSTEM SETTINGS
ZMQ_PORT = 5555
DB_FILENAME = "ai_data.db"
