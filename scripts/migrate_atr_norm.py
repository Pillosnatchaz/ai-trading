"""
ATR Normalization Migration Script
===================================
Recomputes mom_dist_m5, mom_dist_m15, mom_dist_h1, dist_ema_50
from /last_bid to /atr normalization in-place.

Usage:
  python scripts/migrate_atr_norm.py              # dry-run on ai-trading-iso DB
  python scripts/migrate_atr_norm.py --apply      # apply changes
  python scripts/migrate_atr_norm.py --apply --db E:\\Projects\\ai-trading\\ai_data.db

After running --apply on both DBs:
  1. Update feature_builder.py (change /last_bid to /atr)
  2. Retrain both models
"""

import sqlite3
import json
import sys
import shutil
from pathlib import Path

# ponytail: defaults to iso DB, override with --db
DB_PATH = str(Path(__file__).parent.parent / "ai_data.db")
DRY_RUN = True

# Parse args
for i, arg in enumerate(sys.argv[1:], 1):
    if arg == "--apply":
        DRY_RUN = False
    elif arg == "--db" and i < len(sys.argv) - 1:
        DB_PATH = sys.argv[i + 1]
    elif sys.argv[i - 1] == "--db":
        continue  # already consumed

FIELDS_TO_MIGRATE = ['mom_dist_m5', 'mom_dist_m15', 'mom_dist_h1', 'dist_ema_50']
ATR_FLOOR = 0.5

print(f"DB: {DB_PATH}")
print(f"Mode: {'DRY RUN (preview only)' if DRY_RUN else 'APPLY (will modify DB)'}")
print(f"Fields: {FIELDS_TO_MIGRATE}")
print()

# ponytail: back up before touching anything
if not DRY_RUN:
    backup_path = DB_PATH + ".bak_before_atr_norm"
    if not Path(backup_path).exists():
        shutil.copy2(DB_PATH, backup_path)
        print(f"Backup saved: {backup_path}")
    else:
        print(f"Backup already exists: {backup_path}")

conn = sqlite3.connect(DB_PATH, timeout=30)
cur = conn.cursor()

# Get all snapshots with features
cur.execute("""
    SELECT id, price, features_json 
    FROM snapshots 
    WHERE features_json IS NOT NULL
    ORDER BY id
""")
rows = cur.fetchall()
print(f"Total snapshots: {len(rows)}")

skipped_no_atr = 0
skipped_zero_atr = 0
skipped_already = 0
skipped_missing_field = 0
migrated = 0
preview_samples = []

for row_id, price, fj in rows:
    features = json.loads(fj)
    
    # Skip if already migrated
    if features.get('_atr_normalized'):
        skipped_already += 1
        continue
    
    atr = features.get('atr')
    if atr is None:
        skipped_no_atr += 1
        continue
    
    atr = max(float(atr), ATR_FLOOR)
    
    if price is None or price == 0:
        skipped_no_atr += 1
        continue
    
    # Check if all fields exist
    if not all(f in features for f in FIELDS_TO_MIGRATE):
        skipped_missing_field += 1
        continue

    # Recompute: new = old * price / atr
    changed = {}
    for field in FIELDS_TO_MIGRATE:
        old_val = features[field]
        if old_val is None or old_val == 0:
            continue
        new_val = old_val * price / atr
        changed[field] = (old_val, new_val)
        features[field] = new_val

    # Also update rel_h1 alias
    if 'rel_h1' in features and 'mom_dist_h1' in changed:
        features['rel_h1'] = features['mom_dist_h1']

    features['_atr_normalized'] = True

    if len(preview_samples) < 5 and changed:
        preview_samples.append({
            'id': row_id, 'price': price, 'atr': atr,
            'changes': {k: f"{v[0]:.6f} -> {v[1]:.4f}" for k, v in changed.items()}
        })

    if not DRY_RUN:
        cur.execute(
            "UPDATE snapshots SET features_json = ? WHERE id = ?",
            (json.dumps(features), row_id)
        )

    migrated += 1

if not DRY_RUN:
    conn.commit()

conn.close()

# Report
print(f"\nResults:")
print(f"  Migrated:              {migrated}")
print(f"  Skipped (already done): {skipped_already}")
print(f"  Skipped (no ATR/price): {skipped_no_atr}")
print(f"  Skipped (ATR=0, <floor): {skipped_zero_atr}")
print(f"  Skipped (missing field): {skipped_missing_field}")

if preview_samples:
    print(f"\nSample conversions (old -> new):")
    for s in preview_samples:
        print(f"  id={s['id']} price={s['price']:.2f} atr={s['atr']:.2f}")
        for field, change in s['changes'].items():
            print(f"    {field}: {change}")

if DRY_RUN:
    print(f"\n⚠️  DRY RUN — no changes written. Run with --apply to execute.")
else:
    print(f"\n✅ Migration complete. Now:")
    print(f"   1. Update feature_builder.py (change /last_bid to /atr)")
    print(f"   2. Retrain models")
