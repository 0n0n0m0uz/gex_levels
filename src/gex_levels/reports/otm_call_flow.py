"""
otm_call_flow.py - OTM Call Delta-Volume Momentum

Filters OTM calls with delta 0.20-0.40 and computes, for any symbol:
  - Dollar-delta OI: cumulative positioning pressure toward the call wall
  - Dollar-delta Vol: today's actual buying flow
  - Dollar-gamma OI: gamma concentration in the filtered zone
  - Near-term (<=21 DTE) vs far-term (>21 DTE) split within the chosen window
  - Momentum vs the prior run of the same symbol+window

Signal indicates whether buying pressure is building toward the call wall.

Note on --0dte: Black-Scholes delta/gamma get numerically unstable as
DTE->0 (as T->0, d1 blows up unless spot sits very close to strike), so
the delta 0.20-0.40 band may catch few or noisy strikes at DTE=0. Unlike
oi_churn.py, momentum here compares aggregate bucket totals against
whatever was last saved for this exact symbol+window (not a specific
prior calendar day) -- so running --0dte twice in the same session (e.g.
30 min after open, then again near the close) naturally compares this
morning's totals against this afternoon's, which is the only comparison
that makes sense for same-day-expiring contracts.

Usage:
    python reports/otm_call_flow.py SPY                # --days 30 (default)
    python reports/otm_call_flow.py SPY --days 90
    python reports/otm_call_flow.py SPY --0dte
    python reports/otm_call_flow.py AAPL
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone

try:
    import numpy as np
except ImportError as e:
    print(f"Missing dependency: {e}")
    sys.exit(1)

from dotenv import load_dotenv

load_dotenv()

from gex_levels.getData.fetch_spot import get_spot, get_chain, get_risk_free_rate
from gex_levels.black_scholes.black_scholes_calcs import bs_delta, bs_gamma

DELTA_MIN = 0.20
DELTA_MAX = 0.40
OTM_CEILING = 1.25  # strikes up to +25% OTM
NEAR_DTE = 21  # near-term bucket ceiling

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def state_path(symbol):
    return os.path.join(DATA_DIR, f"otm_call_flow_{symbol}.json")


def collect_otm_calls(raw_chain, spot, min_dte, max_dte, risk_free_rate):
    """Filter OTM calls with delta DELTA_MIN-DELTA_MAX from a raw_chain
    (get_chain()'s output: a list of (exp_str, calls_df, puts_df) tuples,
    same shape whether it came from Schwab or yfinance).

    Returns list of dicts per qualifying strike.
    """
    now = datetime.now()
    results = []

    for exp_str, calls_df, _ in raw_chain:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d")
        dte = (exp_date - now).days
        if dte < min_dte or dte > max_dte:
            continue
        T = max(dte, 0.5) / 365.0

        volume_col = "totalVolume" if "totalVolume" in calls_df.columns else "volume"

        otm_mask = (
            (calls_df["strike"] > spot)
            & (calls_df["strike"] < spot * OTM_CEILING)
            & (calls_df["impliedVolatility"] > 0.001)
            & (calls_df["openInterest"] > 0)
        )

        for _, row in calls_df[otm_mask].iterrows():
            K = float(row["strike"])
            iv = float(row["impliedVolatility"])
            oi_raw = row["openInterest"]
            oi = (
                0
                if (oi_raw is None or (isinstance(oi_raw, float) and np.isnan(oi_raw)))
                else int(oi_raw)
            )
            vol_raw = row.get(volume_col, 0)
            vol = (
                0
                if (
                    vol_raw is None
                    or (isinstance(vol_raw, float) and np.isnan(vol_raw))
                )
                else int(vol_raw)
            )

            delta = float(
                bs_delta(
                    spot,
                    np.array([K]),
                    np.array([T]),
                    risk_free_rate,
                    np.array([iv]),
                    is_call=True,
                )[0]
            )
            if not (DELTA_MIN <= delta <= DELTA_MAX):
                continue

            gamma = float(
                bs_gamma(
                    spot,
                    np.array([K]),
                    np.array([T]),
                    risk_free_rate,
                    np.array([iv]),
                )[0]
            )

            results.append(
                {
                    "strike": K,
                    "delta": delta,
                    "gamma": gamma,
                    "oi": oi,
                    "volume": vol,
                    "dte": dte,
                }
            )

    return results


def compute_metrics(rows, spot):
    """Compute dollar-delta and dollar-gamma metrics, split near/far DTE."""
    near = [r for r in rows if r["dte"] <= NEAR_DTE]
    far = [r for r in rows if r["dte"] > NEAR_DTE]

    def bucket(bucket_rows):
        if not bucket_rows:
            return {
                "dollar_delta_oi": 0.0,
                "dollar_delta_vol": 0.0,
                "dollar_gamma_oi": 0.0,
                "count": 0,
            }
        dd_oi = sum(r["delta"] * r["oi"] * spot * 100 for r in bucket_rows)
        dd_vol = sum(r["delta"] * r["volume"] * spot * 100 for r in bucket_rows)
        dg_oi = sum(r["gamma"] * r["oi"] * 100 * spot**2 * 0.01 for r in bucket_rows)
        return {
            "dollar_delta_oi": dd_oi,
            "dollar_delta_vol": dd_vol,
            "dollar_gamma_oi": dg_oi,
            "count": len(bucket_rows),
        }

    return bucket(near), bucket(far), bucket(rows)


def load_prior(symbol, window_key):
    """Last-saved bucket totals for this symbol+window, or None."""
    try:
        with open(state_path(symbol), "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return data.get(window_key)


def save_state(symbol, window_key, entry):
    """Overwrite only this window's slot -- other windows' last-saved
    state for the same symbol are preserved in the same file.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    path = state_path(symbol)
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data[window_key] = entry
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def determine_signal(m_total, m_near, m_far, prior):
    """Derive directional signal from flow metrics and momentum."""
    near_oi = m_near["dollar_delta_oi"]
    far_oi = m_far["dollar_delta_oi"]

    momentum_pct = 0.0
    momentum_str = "N/A (no prior)"
    if prior:
        prev_oi = prior.get("total", {}).get("dollar_delta_oi", 0)
        if prev_oi > 0:
            momentum_pct = (m_total["dollar_delta_oi"] - prev_oi) / prev_oi * 100
            momentum_str = (
                f"+{momentum_pct:.1f}%" if momentum_pct >= 0 else f"{momentum_pct:.1f}%"
            )

    near_dominant = near_oi > far_oi
    flow_rising = momentum_pct > 5 if prior else None
    flow_fading = momentum_pct < -5 if prior else None

    if flow_rising and near_dominant:
        signal = "BULLISH — approaching call wall"
    elif flow_rising and not near_dominant:
        signal = "BULLISH (structural)"
    elif flow_fading:
        signal = "FADING — pressure easing"
    elif near_dominant:
        signal = "NEUTRAL/BULLISH — near-term bid"
    else:
        signal = "NEUTRAL"

    return signal, momentum_str, momentum_pct


def fmt_bn(val):
    abs_val = abs(val)
    sign = "+" if val >= 0 else "-"
    if abs_val >= 1e9:
        return f"{sign}{abs_val / 1e9:.2f}B"
    elif abs_val >= 1e6:
        return f"{sign}{abs_val / 1e6:.1f}M"
    return f"{sign}{abs_val / 1e3:.0f}K"


def print_pinescript_block(symbol, m_near, m_far, m_total, signal, momentum_str, spot, ts):
    sep = "=" * 63
    print()
    print(f"-- PASTE INTO PINE SCRIPT (OTM Call Flow — {symbol}) --")
    print(f"// {sep}")
    print("//  OTM CALL DELTA-VOLUME MOMENTUM — update each morning")
    print(f"// {sep}")
    print(f'var string OCFLOW_SYM      = "{symbol}"')
    print(f'var string OCFLOW_TS       = "{ts}"')
    print(f"var float  OCFLOW_SPOT     = {spot:.2f}")
    print(f"var float  OCFLOW_DD_OI    = {m_total['dollar_delta_oi']:.0f}")
    print(f"var float  OCFLOW_DD_VOL   = {m_total['dollar_delta_vol']:.0f}")
    print(f"var float  OCFLOW_DG_OI    = {m_total['dollar_gamma_oi']:.0f}")
    print(f"var float  OCFLOW_NEAR_OI  = {m_near['dollar_delta_oi']:.0f}")
    print(f"var float  OCFLOW_FAR_OI   = {m_far['dollar_delta_oi']:.0f}")
    print(f'var string OCFLOW_SIGNAL   = "{signal}"')
    print(f'var string OCFLOW_MOMENTUM = "{momentum_str}"')
    print(f"// {sep}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Compare today's OTM call delta/gamma flow vs the prior run (same window) for any symbol.",
        epilog="Examples:\n  python otm_call_flow.py SPY\n  python otm_call_flow.py SPY --days 90\n  python otm_call_flow.py SPY --0dte\n  python otm_call_flow.py AAPL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "symbol", help="Optionable ticker symbol (e.g. SPY, AAPL, NVDA)"
    )
    window_group = parser.add_mutually_exclusive_group()
    window_group.add_argument(
        "--days",
        choices=["30", "90"],
        default=None,
        help="DTE window to compute: 30 or 90. Defaults to 30.",
    )
    window_group.add_argument(
        "--0dte",
        dest="dte_zero",
        action="store_true",
        help="Compute today's 0DTE expiration only, instead of a 30/90-day window.",
    )
    args = parser.parse_args()
    symbol = args.symbol.upper()

    if args.dte_zero:
        window_key = "0dte"
        min_dte, max_dte = 0, 0
    else:
        days = int(args.days) if args.days else 30
        window_key = str(days)
        min_dte, max_dte = 1, days

    window_label = "0DTE" if args.dte_zero else f"DTE {min_dte}-{max_dte}"
    today_str = datetime.now().strftime("%Y-%m-%d")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"OTM Call Flow — {symbol}  |  delta {DELTA_MIN}–{DELTA_MAX}  |  {window_label}\n")

    spot, is_direct_index = get_spot(symbol, today_str)
    print(f"  {symbol}: ${spot:.2f}")

    risk_free_rate, rf_rate_msg = get_risk_free_rate()
    print(rf_rate_msg)

    raw_chain = get_chain(symbol, today_str, max_dte, is_direct_index)
    rows = collect_otm_calls(raw_chain, spot, min_dte, max_dte, risk_free_rate)
    print(
        f"  {len(rows)} qualifying strikes (delta {DELTA_MIN}–{DELTA_MAX}, {window_label})"
    )

    if not rows:
        print(
            "No qualifying strikes found — check market hours or chain availability."
        )
        return

    m_near, m_far, m_total = compute_metrics(rows, spot)
    prior = load_prior(symbol, window_key)
    signal, momentum_str, momentum_pct = determine_signal(m_total, m_near, m_far, prior)

    print()
    print(f"  Dollar-Delta OI  (total):      {fmt_bn(m_total['dollar_delta_oi'])}")
    print(f"  Dollar-Delta Vol (today flow): {fmt_bn(m_total['dollar_delta_vol'])}")
    print(f"  Dollar-Gamma OI  (total):      {fmt_bn(m_total['dollar_gamma_oi'])}")
    print(
        f"  Near-term (≤{NEAR_DTE}d) OI:        {fmt_bn(m_near['dollar_delta_oi'])}  ({m_near['count']} strikes)"
    )
    print(
        f"  Far-term  (>{NEAR_DTE}d) OI:        {fmt_bn(m_far['dollar_delta_oi'])}  ({m_far['count']} strikes)"
    )
    print(f"  Momentum vs prior:             {momentum_str}")
    print(f"  Signal:                        {signal}")

    save_state(
        symbol, window_key, {"date": today_str, "total": m_total, "near": m_near, "far": m_far}
    )
    print(f"\n  State saved → {state_path(symbol)}")

    print_pinescript_block(symbol, m_near, m_far, m_total, signal, momentum_str, spot, ts)
    print("Done.")


if __name__ == "__main__":
    main()
