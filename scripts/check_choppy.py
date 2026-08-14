import sqlite3, json
c = sqlite3.connect(r'E:\Projects\ai-trading-iso\ai_data.db')
rows = c.execute("SELECT profit, features_json FROM live_trades WHERE direction='BUY' AND profit IS NOT NULL ORDER BY timestamp DESC LIMIT 20").fetchall()
for p, f_json in rows:
    f = json.loads(f_json)
    print(f"Profit: {p:>7.2f} | ATR: {f.get('atr'):.2f} | H1: {f.get('rel_h1', 0):>6.2f} | EMA_Dist: {f.get('dist_ema_50', 0):>6.2f} | VolRegime: {f.get('volatility_regime')} | Prob: {f.get('live_prob_buy', 0):.2f}")
