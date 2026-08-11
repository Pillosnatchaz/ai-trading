"""Find optimal asymmetric H1 threshold using CORRECT v4.0 labels (ATR-normalized)."""
import sqlite3, json

DB = r"E:\Projects\ai-trading-iso\ai_data.db"
conn = sqlite3.connect(DB, timeout=30)

rows = conn.execute("""
    SELECT features_json, label, sell_label
    FROM snapshots
    WHERE features_json IS NOT NULL 
      AND (label IS NOT NULL OR sell_label IS NOT NULL)
""").fetchall()
conn.close()

data = []
for fj, buy_l, sell_l in rows:
    f = json.loads(fj)
    rel_h1 = f.get('rel_h1') or f.get('mom_dist_h1')
    if rel_h1 is not None:
        data.append((float(rel_h1), buy_l, sell_l))

# v4.0 mapping: 
# drop -2 (Fast SOTW)
# 1 -> 1 (Win)
# -1, -3, 0 -> 0 (Loss/Timeout)
def map_label(l):
    if l == -2 or l is None: return None
    return 1 if l == 1 else 0

buy_all = [(r, map_label(b)) for r, b, s in data if map_label(b) is not None]
sell_all = [(r, map_label(s)) for r, b, s in data if map_label(s) is not None]

buy_base = sum(1 for _, b in buy_all if b == 1) / len(buy_all) * 100 if buy_all else 0
sell_base = sum(1 for _, s in sell_all if s == 1) / len(sell_all) * 100 if sell_all else 0
print(f"Baseline BUY WR: {buy_base:.1f}% (n={len(buy_all)})")
print(f"Baseline SELL WR: {sell_base:.1f}% (n={len(sell_all)})")

# SELL: WR when shorting into a pump (rel_h1 > threshold)
print(f"\n--- SELL (shorting a pump, rel_h1 > threshold) ---")
print(f"{'Threshold':>10} | {'WR%':>6} | {'n':>6}")
print("-" * 35)
for t in [x * 0.5 for x in range(0, 31)]: 
    subset = [(r, s) for r, s in sell_all if r > t]
    if len(subset) < 10: break
    wr = sum(1 for _, s in subset if s == 1) / len(subset) * 100
    print(f"{t:>10.1f} | {wr:>5.1f}% | {len(subset):>6}")

# BUY: WR when buying a dump (rel_h1 < -threshold)
print(f"\n--- BUY (buying a dump, rel_h1 < -threshold) ---")
print(f"{'Threshold':>10} | {'WR%':>6} | {'n':>6}")
print("-" * 35)
for t in [x * 0.5 for x in range(0, 31)]:
    subset = [(r, b) for r, b in buy_all if r < -t]
    if len(subset) < 10: break
    wr = sum(1 for _, b in subset if b == 1) / len(subset) * 100
    print(f"{-t:>10.1f} | {wr:>5.1f}% | {len(subset):>6}")
