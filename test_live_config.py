"""Pins the label/execution contract that broke on July 17.

The model's probability only means "will a trade with THESE barriers win?" if the
labeler, the calibration purge, the live SL clamp and the EA's pip size all agree.
They live in four different files, so nothing stops one from moving alone — which
is exactly what happened on July 17 (a model trained on 20/40 executing 40/60:
13 trades, 0% win rate).

Run: python test_live_config.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent


def grab(relpath, pattern, cast=float):
    """First regex capture group in a file, cast."""
    text = (ROOT / relpath).read_text(encoding="utf-8", errors="replace")
    m = re.search(pattern, text)
    assert m, f"pattern {pattern!r} not found in {relpath} — did the file move?"
    return cast(m.group(1))


def test_label_execution_contract():
    # --- what the labels were built with ---
    sl = grab("data_engine/run_labeler.py", r"TripleBarrierLabeler\(sl_pips=(\d+)", int)
    tp = grab("data_engine/run_labeler.py", r"TripleBarrierLabeler\(sl_pips=\d+,\s*tp_pips=(\d+)", int)
    max_bars = grab("data_engine/run_labeler.py", r"TripleBarrierLabeler\(sl_pips=\d+,\s*tp_pips=\d+,\s*max_bars=(\d+)", int)

    # --- what the live loop actually sends ---
    lo = grab("orchestration/main_loop.py", r"sl_pips = max\((\d+), min\(\d+,", int)
    hi = grab("orchestration/main_loop.py", r"sl_pips = max\(\d+, min\((\d+),", int)
    ratio = grab("orchestration/main_loop.py", r"tp_pips = round\(sl_pips \* ([\d.]+)\)")

    # --- what the calibration purge assumes ---
    horizon = grab("intelligence/ml_lightgbm.py", r"LABEL_HORIZON = (\d+)", int)

    # --- what the EA calls a pip ---
    ea_pip = grab("MIA_v4_ZMQ_Bridge_Cent.mq4", r"#define PIP ([\d.]+)")
    py_pip = grab("data_engine/triple_barrier.py", r"self\.sl_dist = sl_pips \* ([\d.]+)")

    # 1. live risk:reward must equal the labelled risk:reward, or the 40% breakeven
    #    the threshold is chosen against is simply the wrong number.
    assert abs(ratio - tp / sl) < 1e-9, (
        f"live RR {ratio} != labelled RR {tp}/{sl} = {tp / sl}. "
        f"Relabel and retrain, or set the ratio back."
    )

    # 2. the live SL clamp must bracket the labelled SL. Outside it, every trade
    #    asks the model about barriers it never saw.
    assert lo <= sl <= hi, (
        f"labelled SL {sl} is outside the live clamp {lo}-{hi}. "
        f"Every live trade would use barriers the model was not trained on."
    )

    # 3. the calibration fold purge must match the label horizon, or fold-boundary
    #    rows keep labels decided by prices inside the validation window.
    assert horizon == max_bars, (
        f"LABEL_HORIZON {horizon} != labeler max_bars {max_bars}; "
        f"the TimeSeriesSplit purge is the wrong width."
    )

    # 4. the EA and the labeler must agree on what a pip is, or stops land at the
    #    wrong distance no matter how correct everything upstream is.
    assert abs(ea_pip - py_pip) < 1e-9, (
        f"EA pip {ea_pip} != labeler pip {py_pip}."
    )

    print(f"[+] labels {sl}/{tp} @ {max_bars} bars | live clamp {lo}-{hi} @ RR 1:{ratio} "
          f"| purge {horizon} | pip {py_pip}")


STARTING_BALANCE_USD = 6.00   # Rp100k. raise this when the account is topped up.
MAX_RISK_PCT = 1.0


def test_cent_risk_is_small():
    """Worst-case single trade on the cent account must stay within MAX_RISK_PCT."""
    lot = grab("orchestration/main_loop.py", r"dynamic_lot = ([\d.]+)")
    hi = grab("orchestration/main_loop.py", r"sl_pips = max\(\d+, min\((\d+),", int)
    # cent: 1.00 lot = 1 oz gold -> $0.10 per pip (pip = 0.1 price).
    # ponytail: confirm the contract size on HFM's spec page before funding.
    worst = hi * lot * 0.10
    pct = worst / STARTING_BALANCE_USD * 100
    assert lot <= 0.01, f"lot {lot} above the cent live-test cap of 0.01"
    assert pct <= MAX_RISK_PCT, (
        f"worst-case trade risks ${worst:.3f} = {pct:.1f}% of ${STARTING_BALANCE_USD}, "
        f"over the {MAX_RISK_PCT}% cap"
    )
    print(f"[+] cent risk: {lot} lot x {hi}p worst case = ${worst:.3f} "
          f"({pct:.1f}% of ${STARTING_BALANCE_USD:.2f})")


if __name__ == "__main__":
    test_label_execution_contract()
    test_cent_risk_is_small()
    print("[+] live config OK")
