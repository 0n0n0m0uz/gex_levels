"""
otm_call_flow_spx.py - OTM Call Delta-Volume Momentum for SPX (via SPY)

Filters OTM calls with delta 0.20-0.40 (excluding 0DTE) and computes:
  - Dollar-delta OI: cumulative positioning pressure toward the call wall
  - Dollar-delta Vol: today's actual buying flow
  - Dollar-gamma OI: gamma concentration in the filtered zone
  - Near-term (1-21 DTE) vs far-term (22-90 DTE) split
  - Day-over-day momentum vs prior session

Signal indicates whether buying pressure is building toward the call wall.

Usage:
    python volume/otm_call_flow_spx.py
"""

import os
import sys
import json
from datetime import datetime, timezone


try:
    import numpy as np
    from scipy.stats import norm
    import yfinance as yf
except ImportError as e:
    print(f"Missing dependency: {e}")
    sys.exit(1)

from gex_levels.config import RISK_FREE_RATE
from gex_levels.black_scholes.black_scholes_calcs import bs_delta, bs_gamma

ETF = "SPY"
INDEX_TICKER = "^GSPC"

DELTA_MIN = 0.20
DELTA_MAX = 0.40
MIN_DTE = 1  # exclude 0DTE
MAX_DTE = 90
NEAR_DTE = 21  # near-term bucket ceiling

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STATE_FILE = os.path.join(DATA_DIR, "otm_call_flow_spx.json")


def fetch_spot():
    """Fetch SPY spot and SPX index price. Returns (spot_etf, spot_spx, ratio)."""
    ticker = yf.Ticker(ETF)
    spot_etf = None
    try:
        hist = ticker.history(period="1d", interval="1m")
        if not hist.empty:
            spot_etf = float(hist["Close"].iloc[-1])
    except Exception:
        pass
    if not spot_etf or spot_etf <= 0:
        spot_etf = ticker.fast_info["lastPrice"]

    idx = yf.Ticker(INDEX_TICKER)
    spot_spx = float(idx.fast_info["lastPrice"])
    ratio = spot_spx / spot_etf
    return spot_etf, spot_spx, ratio


def collect_otm_calls(ticker, spot_etf):
    """Fetch all OTM SPY calls with delta 0.20-0.40, DTE 1-90.

    Returns list of dicts per qualifying strike.
    """
    now = datetime.now()
    results = []

    for exp_str in ticker.options:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d")
        dte = (exp_date - now).days
        if dte < MIN_DTE or dte > MAX_DTE:
            continue
        T = max(dte, 0.5) / 365.0

        try:
            chain = ticker.option_chain(exp_str)
        except Exception as e:
            print(f"  Skip {exp_str}: {e}")
            continue

        calls = chain.calls
        otm_mask = (
            (calls["strike"] > spot_etf)
            & (calls["strike"] < spot_etf * 1.25)
            & (calls["impliedVolatility"] > 0.001)
            & (calls["openInterest"] > 0)
        )

        for _, row in calls[otm_mask].iterrows():
            K = float(row["strike"])
            iv = float(row["impliedVolatility"])
            oi_raw = row["openInterest"]
            oi = (
                0
                if (oi_raw is None or (isinstance(oi_raw, float) and np.isnan(oi_raw)))
                else int(oi_raw)
            )
            vol_raw = row.get("volume", 0)
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
                    spot_etf,
                    np.array([K]),
                    np.array([T]),
                    RISK_FREE_RATE,
                    np.array([iv]),
                    is_call=True,
                )[0]
            )
            if not (DELTA_MIN <= delta <= DELTA_MAX):
                continue

            gamma = float(
                bs_gamma(
                    spot_etf,
                    np.array([K]),
                    np.array([T]),
                    RISK_FREE_RATE,
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


def compute_metrics(rows, spot_etf):
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
        dd_oi = sum(r["delta"] * r["oi"] * spot_etf * 100 for r in bucket_rows)
        dd_vol = sum(r["delta"] * r["volume"] * spot_etf * 100 for r in bucket_rows)
        dg_oi = sum(
            r["gamma"] * r["oi"] * 100 * spot_etf**2 * 0.01 for r in bucket_rows
        )
        return {
            "dollar_delta_oi": dd_oi,
            "dollar_delta_vol": dd_vol,
            "dollar_gamma_oi": dg_oi,
            "count": len(bucket_rows),
        }

    return bucket(near), bucket(far), bucket(rows)


def load_prior():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_state(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
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


def print_pinescript_block(m_near, m_far, m_total, signal, momentum_str, spot_spx, ts):
    sep = "=" * 63
    print()
    print("-- PASTE INTO PINE SCRIPT (OTM Call Flow — SPX) --")
    print(f"// {sep}")
    print("//  OTM CALL DELTA-VOLUME MOMENTUM — update each morning")
    print(f"// {sep}")
    print('var string OCFLOW_SYM      = "SPX"')
    print(f'var string OCFLOW_TS       = "{ts}"')
    print(f"var float  OCFLOW_SPOT     = {spot_spx:.2f}")
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
    today_str = datetime.now().strftime("%Y-%m-%d")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(
        f"OTM Call Flow — SPX  |  delta {DELTA_MIN}–{DELTA_MAX}  |  DTE {MIN_DTE}–{MAX_DTE}\n"
    )

    print("[SPY] Fetching spot...")
    spot_etf, spot_spx, ratio = fetch_spot()
    print(f"  SPY: ${spot_etf:.2f}  |  SPX: {spot_spx:.2f}  (ratio {ratio:.4f}x)")

    print("[SPY] Fetching options chain (this takes ~30s)...")
    ticker = yf.Ticker(ETF)
    rows = collect_otm_calls(ticker, spot_etf)
    print(
        f"  {len(rows)} qualifying strikes (delta {DELTA_MIN}–{DELTA_MAX}, DTE {MIN_DTE}–{MAX_DTE})"
    )

    if not rows:
        print(
            "No qualifying strikes found — check market hours or SPY chain availability."
        )
        return

    m_near, m_far, m_total = compute_metrics(rows, spot_etf)
    prior = load_prior()
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

    save_state({"date": today_str, "total": m_total, "near": m_near, "far": m_far})
    print(f"\n  State saved → {STATE_FILE}")

    print_pinescript_block(m_near, m_far, m_total, signal, momentum_str, spot_spx, ts)
    print("Done.")


if __name__ == "__main__":
    main()
