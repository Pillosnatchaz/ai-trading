import sqlite3, json

DB = r"E:\Projects\ai-trading-iso\ai_data.db"
conn = sqlite3.connect(DB, timeout=30)
rows = conn.execute("SELECT features_json, label FROM snapshots WHERE features_json IS NOT NULL AND label IS NOT NULL AND label != -2").fetchall()
conn.close()

buy_all = []
for fj, b in rows:
    f = json.loads(fj)
    rel_h1 = f.get('rel_h1') or f.get('mom_dist_h1')
    if rel_h1 is not None:
        buy_all.append((float(rel_h1), 1 if b == 1 else 0))

print("\n--- BUY (trend following a pump, rel_h1 > threshold) ---")
for t in [0.0, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0]:
    subset = [(r, b) for r, b in buy_all if r > t]
    if not subset: break
    wr = sum(1 for _, b in subset if b == 1) / len(subset) * 100
    print(f"{t:>10.1f} | {wr:>5.1f}% | {len(subset):>6}")
