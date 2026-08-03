"""
compare_greeks.py - Schwab greeks vs Black-Scholes greeks, per-symbol sanity check

For near-ATM strikes, compares Schwab's pre-computed delta/gamma against
Black-Scholes values computed from the same chain response. Every compared
strike is saved to a CSV in reports/data/; only strikes whose delta or
gamma diff exceeds DELTA_DIFF_THRESHOLD/GAMMA_DIFF_THRESHOLD print to the
terminal, so a wide window doesn't bury the rows worth looking at.

Spot, dividend yield, and risk-free rate are all read from the chain
response itself -- the same values Schwab used internally to compute its
greeks -- rather than separately fetched/static inputs, so any observed
diff is attributable to the BS formula itself, not mismatched inputs:
  - Spot: chain response's `underlyingPrice`.
  - Dividend yield: chain response's `dividendYield` (real per-symbol data
    for equities/ETFs; not populated for direct-index symbols like SPX/NDX,
    where it falls back to --div-yield).
  - Risk-free rate: chain response's `interestRate`, falling back to the
    project's static RISK_FREE_RATE constant only if Schwab reports none.
    A warning prints if the two differ significantly, since that gap
    itself would show up as a spurious delta/gamma diff below.
Both fallback decisions are printed each run so you can see which source
was actually used.

Usage:
    python reports/compare_greeks.py SPY                # --days 30 (default)
    python reports/compare_greeks.py SPY --days 90
    python reports/compare_greeks.py SPX --div-yield 0.013
    python reports/compare_greeks.py AAPL --div-yield 0.0
"""

import os
import sys
import csv
import argparse
from datetime import datetime, timedelta

import numpy as np
from scipy.stats import norm
from dotenv import load_dotenv

load_dotenv()

from gex_levels.config import RISK_FREE_RATE, SCHWAB_DIRECT_INDEX
from gex_levels.auth.api_auth_schwab import schwab_get

ATM_BAND = 0.03  # show strikes within +-3% of spot
DEFAULT_DIVIDEND_YIELD = 0.012  # fallback when Schwab reports none (e.g. SPX/NDX/VIX)
RFR_WARN_THRESHOLD = 0.0025  # warn if Schwab's interestRate vs RISK_FREE_RATE gap exceeds 25bp
DELTA_DIFF_THRESHOLD = 0.05  # flag rows where |sch_delta - bs_delta| exceeds this
GAMMA_DIFF_THRESHOLD = 0.01  # flag rows where |sch_gamma - bs_gamma| exceeds this

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

CSV_FIELDS = [
    "exp", "type", "strike", "dte",
    "sch_delta", "bs_delta", "d_diff",
    "sch_gamma", "bs_gamma", "g_diff",
]


def csv_path(symbol, window_key, ts):
    return os.path.join(DATA_DIR, f"compare_greeks_{symbol}_{window_key}_{ts}.csv")


def save_csv(path, rows):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def bs_delta_q(S, K, T, r, q, sigma, is_call=True):
    """Black-Scholes delta with a continuous dividend yield q."""
    d1 = (np.log(S / K) + (r - q + sigma**2 / 2) * T) / (sigma * np.sqrt(T))
    disc_q = np.exp(-q * T)
    return disc_q * norm.cdf(d1) if is_call else disc_q * (norm.cdf(d1) - 1.0)


def bs_gamma_q(S, K, T, r, q, sigma):
    """Black-Scholes gamma with a continuous dividend yield q."""
    d1 = (np.log(S / K) + (r - q + sigma**2 / 2) * T) / (sigma * np.sqrt(T))
    return np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))


def fetch_schwab_chain(schwab_symbol, max_dte):
    today = datetime.now()
    to_date = today + timedelta(days=max_dte)
    return schwab_get(
        "https://api.schwabapi.com/marketdata/v1/chains",
        {
            "symbol": schwab_symbol,
            "range": "NTM",
            "strikeCount": 40,
            "fromDate": today.strftime("%Y-%m-%d"),
            "toDate": to_date.strftime("%Y-%m-%d"),
        },
    )


def main():
    parser = argparse.ArgumentParser(
        description="Compare Schwab's pre-computed greeks against this project's "
        "Black-Scholes formula, using Schwab's own spot/IV for each contract.",
        epilog="Examples:\n"
        "  python compare_greeks.py SPY\n"
        "  python compare_greeks.py SPY --days 90\n"
        "  python compare_greeks.py SPX --div-yield 0.013\n"
        "  python compare_greeks.py AAPL --div-yield 0.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("symbol", help="Ticker symbol (e.g. SPY, SPX, AAPL, NVDA)")
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
        help="Compare today's 0DTE expiration only, instead of a 30/90-day window.",
    )
    parser.add_argument(
        "--div-yield",
        type=float,
        default=None,
        help="Override the dividend yield used in the BS formula. Omit to "
        "auto-use Schwab's own per-symbol dividendYield when it reports one "
        f"(equities/ETFs), falling back to {DEFAULT_DIVIDEND_YIELD} when it "
        "doesn't (e.g. SPX/NDX/VIX).",
    )
    args = parser.parse_args()
    symbol = args.symbol.upper()
    schwab_symbol = SCHWAB_DIRECT_INDEX.get(symbol, symbol)

    if args.dte_zero:
        window_key = "0dte"
        window_label = "0DTE"
        min_dte, max_dte = 0, 0
    else:
        days = int(args.days) if args.days else 30
        window_key = str(days)
        window_label = f"DTE 1-{days}"
        min_dte, max_dte = 1, days

    print(f"Greeks Comparison — Schwab vs Black-Scholes ({symbol}, {window_label})\n")

    print(f"Fetching {schwab_symbol} chain from Schwab...")
    data = fetch_schwab_chain(schwab_symbol, max_dte)

    spot = data.get("underlyingPrice")
    if not spot:
        print(
            f"No underlyingPrice/contracts for {schwab_symbol} in this window "
            "— market closed or no expiration in range."
        )
        return
    spot = float(spot)
    print(f"Spot: ${spot:.2f}  (Schwab underlyingPrice)")

    schwab_div_yield = data.get("dividendYield")
    if args.div_yield is not None:
        div_yield = args.div_yield
        print(f"Dividend yield: {div_yield:.3%}  (--div-yield override)")
    elif schwab_div_yield:
        div_yield = schwab_div_yield / 100.0
        print(f"Dividend yield: {div_yield:.3%}  (Schwab dividendYield)")
    else:
        div_yield = DEFAULT_DIVIDEND_YIELD
        print(
            f"Dividend yield: {div_yield:.3%}  (default fallback — Schwab "
            f"reported none for {schwab_symbol})"
        )

    schwab_rate = data.get("interestRate")
    if schwab_rate is not None:
        rfr = schwab_rate / 100.0
        print(f"Risk-free rate: {rfr:.3%}  (Schwab interestRate)")
        rate_gap = abs(rfr - RISK_FREE_RATE)
        if rate_gap >= RFR_WARN_THRESHOLD:
            print(
                f"  WARNING: Schwab's interestRate ({rfr:.3%}) differs from this "
                f"project's RISK_FREE_RATE config constant ({RISK_FREE_RATE:.3%}) "
                f"by {rate_gap:.3%} (threshold: {RFR_WARN_THRESHOLD:.3%}) — that gap "
                "alone would show up as a delta/gamma diff below, separate from any "
                "real BS-formula discrepancy."
            )
            try:
                reply = input("  Continue anyway? [y/N]: ").strip().lower()
            except EOFError:
                reply = ""
            if reply != "y":
                print("  Aborted.")
                sys.exit(1)
    else:
        rfr = RISK_FREE_RATE
        print(f"Risk-free rate: {rfr:.3%}  (RISK_FREE_RATE fallback — Schwab reported none)")
    print()

    now = datetime.now()

    rows = []
    for map_key, opt_type in [("callExpDateMap", "call"), ("putExpDateMap", "put")]:
        for exp_key, strikes in data.get(map_key, {}).items():
            exp_str = exp_key.split(":")[0]
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d")
            dte = (exp_date.date() - now.date()).days
            if dte < min_dte or dte > max_dte:
                continue
            exp_dt = exp_date.replace(hour=16)  # options expire at market close
            days_remaining = (exp_dt - now).total_seconds() / 86400
            T = max(days_remaining, 0.5) / 365.0

            for strike_str, contracts in strikes.items():
                for opt in contracts:
                    strike = float(opt.get("strikePrice", 0))
                    if not (spot * (1 - ATM_BAND) <= strike <= spot * (1 + ATM_BAND)):
                        continue

                    iv = float(opt.get("volatility") or 0) / 100.0
                    sch_delta = opt.get("delta")
                    sch_gamma = opt.get("gamma")

                    if iv <= 0 or sch_delta is None or sch_gamma is None:
                        continue

                    sch_delta = float(sch_delta)
                    sch_gamma = float(sch_gamma)
                    is_call = opt_type == "call"

                    bs_d = float(
                        bs_delta_q(
                            spot, strike, T, rfr, div_yield, iv, is_call=is_call
                        )
                    )
                    bs_g = float(bs_gamma_q(spot, strike, T, rfr, div_yield, iv))
                    d_diff = sch_delta - bs_d
                    g_diff = sch_gamma - bs_g

                    rows.append(
                        {
                            "exp": exp_str,
                            "type": opt_type,
                            "strike": strike,
                            "dte": dte,
                            "sch_delta": sch_delta,
                            "bs_delta": bs_d,
                            "d_diff": d_diff,
                            "sch_gamma": sch_gamma,
                            "bs_gamma": bs_g,
                            "g_diff": g_diff,
                        }
                    )

    if not rows:
        print(
            "No qualifying strikes found — check market hours, ATM_BAND, or chain availability."
        )
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = csv_path(symbol, window_key, ts)
    save_csv(out_path, rows)
    print(f"Compared {len(rows)} strikes — full results saved to {out_path}\n")

    flagged = [
        r
        for r in rows
        if abs(r["d_diff"]) >= DELTA_DIFF_THRESHOLD
        or abs(r["g_diff"]) >= GAMMA_DIFF_THRESHOLD
    ]

    if not flagged:
        print(
            f"No significant differences (delta ±{DELTA_DIFF_THRESHOLD:.2f}, "
            f"gamma ±{GAMMA_DIFF_THRESHOLD:.3f}) — all {len(rows)} strikes within threshold."
        )
        return

    print(
        f"{len(flagged)} of {len(rows)} strikes exceeded significance thresholds "
        f"(delta ±{DELTA_DIFF_THRESHOLD:.2f}, gamma ±{GAMMA_DIFF_THRESHOLD:.3f}):\n"
    )
    print(
        f"{'Exp':>12} {'Type':>5} {'Strike':>8} {'DTE':>4} "
        f"{'SCH_Delta':>10} {'BS_Delta':>10} {'D_Diff':>8} "
        f"{'SCH_Gamma':>10} {'BS_Gamma':>10} {'G_Diff':>8}"
    )
    print("-" * 100)
    for r in flagged:
        print(
            f"{r['exp']:>12} {r['type']:>5} {r['strike']:>8.1f} {r['dte']:>4} "
            f"{r['sch_delta']:>10.4f} {r['bs_delta']:>10.4f} {r['d_diff']:>+8.4f} "
            f"{r['sch_gamma']:>10.6f} {r['bs_gamma']:>10.6f} {r['g_diff']:>+8.6f}"
        )


if __name__ == "__main__":
    main()
