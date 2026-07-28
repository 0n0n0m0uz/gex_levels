# Checks cache for previously existing data, if it doesnt exist fetches spot price and spot interest rates from schwab or yfinance


from datetime import datetime

import numpy as np
import requests
import yfinance as yf

from rich.console import Console

from gex_levels.config import (
    RISK_FREE_RATE,
    SCHWAB_DIRECT_INDEX,
    YFINANCE_DIRECT_INDEX,
    DTE_TAU_30,
    DTE_TAU_90,
    _CHAIN_CACHE,
    _SCHWAB_SPOT_CACHE,
    _SCHWAB_FETCH_FAILED,
)
from gex_levels.getData.fetch_schwab_data import (
    fetch_schwab_spot,
    fetch_schwab_chain,
)
from gex_levels.getData.fetch_yfinance_data import (
    fetch_yfinance_spot,
    fetch_yfinance_chain,
)

console = Console(force_terminal=True)

def get_risk_free_rate():

    """Live risk-free rate from SOFR (Fed FRED API), falling back to the default (placed in an ENV VAR)
    if the fetch fails.
    """

    try:
        r = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR", timeout=10
        )
        sofr = float(r.text.strip().split("\n")[-1].split(",")[1]) / 100
        rf_rate_msg = (f"  {'Risk-Free Rate':<22} {sofr:.2%} (SOFR)")
        #console.print(f"  {'Risk-Free Rate':<22} {sofr:.2%} (SOFR)")
        return sofr, rf_rate_msg
    except Exception:
        rf_rate_msg = (f"  {'Risk-Free Rate':<22}{RISK_FREE_RATE:.2%} (fallback — SOFR unavailable)")
        #console.print(f"  {'Risk-Free Rate':<22}{RISK_FREE_RATE:.4f} (fallback — SOFR unavailable)")
        return RISK_FREE_RATE, rf_rate_msg


def get_spot(symbol, today_str):

    """Resolve spot for `symbol`, trying cache -> Schwab -> yfinance in that
    order. Independent of get_chain() — no shared state between the two
    beyond each having its own cache.

    Returns (spot, is_direct_index).
    """
    is_direct_index = symbol in SCHWAB_DIRECT_INDEX
    schwab_symbol = SCHWAB_DIRECT_INDEX.get(symbol, symbol)
    cache_key = (symbol, today_str)

    if cache_key in _SCHWAB_SPOT_CACHE:
        # Reuse the same spot across the 30d/90d passes — avoids a second
        # Schwab call and keeps both windows consistent.
        spot = _SCHWAB_SPOT_CACHE[cache_key]
        print(f"Reusing cached {schwab_symbol} spot: {spot:.2f}")
        return spot, is_direct_index

    try:
        console.print()
        console.print(
            f"[bold italic grey42]Fetching {schwab_symbol} spot from Schwab[/bold italic grey42]"
        )

        spot = fetch_schwab_spot(schwab_symbol)
        _SCHWAB_SPOT_CACHE[cache_key] = spot
        return spot, is_direct_index

    except Exception as e:
        if is_direct_index:
            # No ETF proxy for a pure index — fall back to yfinance's own
            # ^-prefixed index ticker (e.g. "SPX" -> "^SPX") instead of
            # substituting a different symbol.
            yf_symbol = YFINANCE_DIRECT_INDEX.get(symbol, symbol)
            print(
                f"  Schwab spot fetch failed ({e}) — falling back to yfinance for {yf_symbol}"
            )
            spot = fetch_yfinance_spot(yf_symbol)
            return spot, is_direct_index
        print(
            f"  Schwab spot fetch failed ({e}) — falling back to yfinance for {symbol}"
        )
        spot = fetch_yfinance_spot(symbol)
        return spot, is_direct_index


def get_chain(symbol, today_str, max_dte, is_direct_index):

    """Resolve the raw chain for `symbol`, trying cache -> Schwab -> yfinance in that order.

    Independent of get_spot().

    Returns raw_chain — a list of (exp_str, calls_df, puts_df) tuples — the same shape whether
    it came from Schwab or yfinance — ready to pass straight into collect_chain().
    """
    schwab_symbol = SCHWAB_DIRECT_INDEX.get(symbol, symbol)
    cache_key = (symbol, today_str)

    if cache_key in _CHAIN_CACHE:
        print(f"Reusing cached {schwab_symbol} chain")
        return _CHAIN_CACHE[cache_key]

    if cache_key in _SCHWAB_FETCH_FAILED:
        yf_symbol = YFINANCE_DIRECT_INDEX.get(symbol, symbol) if is_direct_index else symbol
        print(f"  Schwab chain fetch already failed this run — using {yf_symbol} via yfinance")
        return fetch_yfinance_chain(yf_symbol, today_str)

    try:
        console.print()
        console.print(
            f"[bold italic grey42]Fetching {schwab_symbol} chain from Schwab[/bold italic grey42]"
        )

        raw_chain = fetch_schwab_chain(schwab_symbol, today_str, max_dte)
        _CHAIN_CACHE[cache_key] = raw_chain
        return raw_chain

    except Exception as e:
        if is_direct_index:
            yf_symbol = YFINANCE_DIRECT_INDEX.get(symbol, symbol)
            print(
                f"  Schwab chain fetch failed ({e}) — falling back to yfinance for {yf_symbol}"
            )
            _SCHWAB_FETCH_FAILED.add(cache_key)
            return fetch_yfinance_chain(yf_symbol, today_str)
        print(
            f"  Schwab chain fetch failed ({e}) — falling back to yfinance for {symbol}"
        )
        _SCHWAB_FETCH_FAILED.add(cache_key)
        return fetch_yfinance_chain(symbol, today_str)


def collect_chain(raw_chain, spot, max_dte, dte_tau=None):

    """
    2nd step where biz logic (filtering) is applied to the raw native data format and results are
    converted to separate np.arrays for more efficient transformation and calcs of Black Scholes

    Build DTE-weighted options arrays from already-resolved chain data (see
    get_chain() above for how `raw_chain` is obtained).

    Returns np.arrays (calls, puts, num_expirations) w 4 cols: [strike, weighted_OI, T_years, implied_vol]

    Fixes vs original:
    - dte < 0 (not <=) so 0DTE is included and gets maximum decay weight
    - ±20% OTM filter (was ±30% — too wide, pollutes gamma profile with junk)
    - T floored at 0.5/365 so gamma doesn't blow up for same-day expiry
    - Chain downloaded once and reused for both 30d and 90d passes
    """

    if dte_tau is None:
        dte_tau = DTE_TAU_30 if max_dte <= 30 else DTE_TAU_90

    now = datetime.now()
    calls_list, puts_list = [], []
    num_expirations = 0

    for exp_str, calls_df, puts_df in raw_chain:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d")
        dte = (exp_date - now).days
        if dte < 0 or dte > max_dte:
            continue
        T = max(dte, 0.5) / 365.0  # floor at half-day to keep gamma finite
        dte_weight = np.exp(-dte / dte_tau)
        num_expirations += 1

        for df, out_list in [(calls_df, calls_list), (puts_df, puts_list)]:
            mask = (
                (df["impliedVolatility"] > 0.001)
                & (df["openInterest"] > 0)
                & (df["strike"] > 0)
                & (df["strike"] > spot * 0.80)  # ±20% (was ±30%)
                & (df["strike"] < spot * 1.20)
            )
            for _, row in df[mask].iterrows():
                out_list.append(
                    [
                        row["strike"],
                        row["openInterest"] * dte_weight,
                        T,
                        row["impliedVolatility"],
                    ]
                )

    calls = np.array(calls_list) if calls_list else np.empty((0, 4))
    puts = np.array(puts_list) if puts_list else np.empty((0, 4))
    return calls, puts, num_expirations




def get_index_ratio(index_ticker, spot, symbol):

    """Fetch the live index/ETF ratio for --index conversion (e.g. SPY -> ^GSPC).

    Returns (ratio, index_price), or (None, None) if the fetch failed.

    """
    try:
        idx = yf.Ticker(index_ticker)
        index_price = idx.fast_info["lastPrice"]
        ratio = index_price / spot
        print(f"  Index {index_ticker}: {index_price:.2f} (ratio {ratio:.2f}x)")
        return ratio, index_price
    except Exception as e:
        console.print(
            f"[bold italic grey42]Warning: could not fetch {index_ticker}, levels stay in {symbol} price space: {e}[/bold italic grey42]"
        )
        return None, None
