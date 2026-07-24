"""
ponytail: SL/TP Grid Search Optimizer
Simulates multiple SL/TP setups against historical data using pessimistic OHLC labeling.
Outputs a scoreboard to pick the winning ratio.
"""
import sqlite3
import pandas as pd
import os
from data_engine.triple_barrier import TripleBarrierLabeler

def run_grid_search(db_filename='ai_data.db'):
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), db_filename)
    conn = sqlite3.connect(db_path)
    # ponytail: demo mode - grab the last 5000 rows to see the concept, even if it's close-only data
    df = pd.read_sql_query("SELECT price, high, low FROM snapshots ORDER BY id DESC LIMIT 5000", conn)
    df = df.iloc[::-1].reset_index(drop=True) # Reverse to chronological order
    conn.close()

    # df = pd.read_sql_query("SELECT price, high, low FROM snapshots WHERE high IS NOT NULL ORDER BY id ASC", conn)

    prices = df['price'].values
    highs = df['high'].fillna(df['price']).values
    lows = df['low'].fillna(df['price']).values

    has_ohlc = df['high'].notna().sum()
    print(f"[*] Loaded {len(prices)} rows ({has_ohlc} with OHLC data)")
    print()

    # ponytail: grid of SL/TP combos to test
    configs = [
        (20, 30,  "20/30  (1:1.5 Tight)"),
        (20, 40,  "20/40  (1:2 Current)"),
        (30, 45,  "30/45  (1:1.5 Live)"),
        (30, 60,  "30/60  (1:2 Wide)"),
        (40, 60,  "40/60  (1:1.5 Fat)"),
        (15, 22,  "15/22  (1:1.5 Micro)"),
        (25, 37,  "25/37  (1:1.5 Mid)"),
    ]

    print(f"{'Setup':<25} | {'Dir':<4} | {'WR%':>6} | {'Wins':>5} | {'Losses':>6} | {'SOTW':>5} | {'Timeout':>7} | {'Net$/100':>8}")
    print("-" * 100)

    results = []

    for sl, tp, name in configs:
        labeler = TripleBarrierLabeler(sl_pips=sl, tp_pips=tp, max_bars=60)

        for direction in ['buy', 'sell']:
            stats = {1: 0, -1: 0, -2: 0, -3: 0, 0: 0}

            for i in range(len(prices) - labeler.max_bars):
                current_price = prices[i]
                future_prices = prices[i+1 : i+1+labeler.max_bars]
                future_highs = highs[i+1 : i+1+labeler.max_bars]
                future_lows = lows[i+1 : i+1+labeler.max_bars]

                label = labeler.get_label(current_price, future_prices, direction=direction,
                                          future_highs=future_highs, future_lows=future_lows)
                stats[label] += 1

            total = stats[1] + stats[-1] + stats[-2] + stats[-3]
            wr = (stats[1] / total * 100) if total > 0 else 0
            sotw = stats[-2] + stats[-3]

            # ponytail: calculate net profit per 100 trades at 0.01 lot
            # Win = +tp*0.1 per pip, Loss = -sl*0.1 per pip (for 0.01 lot, 1 pip = $0.10)
            profit_per_win = tp * 0.10
            loss_per_loss = sl * 0.10
            net_per_100 = (wr/100 * profit_per_win * 100) - ((100 - wr)/100 * loss_per_loss * 100)

            print(f"{name:<25} | {direction.upper():<4} | {wr:>5.1f}% | {stats[1]:>5} | {stats[-1]:>6} | {sotw:>5} | {stats[0]:>7} | ${net_per_100:>+7.1f}")
            results.append((name, direction, wr, net_per_100, sl, tp))

        print("-" * 100)

    # ponytail: find the best combined (buy+sell average) setup
    print("\n[+] --- BEST SETUPS BY NET PROFIT ---")
    combo_scores = {}
    for name, direction, wr, net, sl, tp in results:
        if name not in combo_scores:
            combo_scores[name] = {'net': 0, 'wr': 0, 'sl': sl, 'tp': tp}
        combo_scores[name]['net'] += net
        combo_scores[name]['wr'] += wr

    sorted_combos = sorted(combo_scores.items(), key=lambda x: x[1]['net'], reverse=True)
    for rank, (name, data) in enumerate(sorted_combos, 1):
        avg_wr = data['wr'] / 2
        print(f"  #{rank} {name}: Avg WR={avg_wr:.1f}%, Combined Net/100=${data['net']:+.1f}")

    winner = sorted_combos[0]
    print(f"\n[WINNER] {winner[0]} (SL={winner[1]['sl']} / TP={winner[1]['tp']})")

if __name__ == "__main__":
    run_grid_search()
