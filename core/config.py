# ==========================================
# MIA v3.0 - CENTRALIZED SETTINGS
# ==========================================

# 1. LIGHTGBM ML SETTINGS
# ponytail: 5,600+ clean OHLC rows — stay at depth 5 until 8k+ rows
LGBM_ESTIMATORS = 100
LGBM_LEARNING_RATE = 0.05
LGBM_MAX_DEPTH = 5

# 2. SYSTEM SETTINGS
ZMQ_PORT = 5555
DB_FILENAME = "ai_data.db"

# 3. NEWS EMBARGO SETTINGS
FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
NEWS_EMBARGO_BEFORE_MIN = 30   # minutes before Red Folder event
NEWS_EMBARGO_AFTER_MIN = 60    # minutes after Red Folder event
