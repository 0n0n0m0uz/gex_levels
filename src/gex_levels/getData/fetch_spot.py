# Checks cache for previously existing data, if it doesnt exist fetches spot price and spot interest rates from schwab or yfinance


from datetime import datetime

import numpy as np
import requests
import yfinance as yf

from rich.console import Console

from gex_levels.config import (
    RISK_FREE_RATE,
    SCHWAB_DIRECT_INDEX,
    SCHWAB_VOL_SYMBOL,
    DTE_TAU_30,
    DTE_TAU_90,
    _CHAIN_CACHE,
    _SCHWAB_SPOT_CACHE,
    _SCHWAB_FETCH_FAILED,
)
from gex_levels.getData.fetch_schwab_data import (
    fetch_schwab_spot,
    fetch_schwab_chain,
    fetch_schwab_quote_close,
)
from gex_levels.getData.fetch_yfinance_data import (
    fetch_yfinance_spot,
    fetch_yfinance_chain,
)

console = Console(force_terminal=True)


def _get_cached_or_schwab_spot(symbol, today_str, is_direct_index):
    """Try the shared spot cache, then Schwab's single-symbol quote endpoint
    (independent of chain-fetching). Populates _SCHWAB_SPOT_CACHE on a fresh
    fetch. Returns spot, or None if Schwab fetch failed and the yfinance
    fallback is needed.
    """
    schwab_symbol = SCHWAB_DIRECT_INDEX.get(symbol, symbol)
    cache_key = (symbol, today_str)

    if cache_key in _SCHWAB_SPOT_CACHE:
        # Reuse the same spot across the 30d/90d passes — avoids a second
        # Schwab call and keeps both windows consistent.
        spot = _SCHWAB_SPOT_CACHE[cache_key]
        print(f"Reusing cached {schwab_symbol} spot: {spot:.2f}")
        return spot

    try:
        console.print()
        console.print(
            f"[bold italic grey42]Fetching {schwab_symbol} spot from Schwab[/bold italic grey42]"
        )

        spot = fetch_schwab_spot(schwab_symbol)
        _SCHWAB_SPOT_CACHE[cache_key] = spot
        return spot

    except Exception as e:
        if is_direct_index:
            # No ETF proxy exists for a pure index under this design —
            # falling back would mean silently substituting a different
            # symbol, which is exactly what we're trying not to do.
            raise ValueError(
                f"Could not fetch {schwab_symbol} spot from Schwab ({e}) — "
                f"no fallback available for {symbol} (it has no ETF proxy)"
            )
        print(
            f"  Schwab spot fetch failed ({e}) — falling back to yfinance for {symbol}"
        )
        return None


def _get_cached_or_schwab_chain(symbol, today_str, max_dte, is_direct_index):
    """Try the shared chain cache, then Schwab's chains endpoint —
    independent of spot-fetching. Populates _CHAIN_CACHE on a fresh fetch.
    Returns raw, or None if Schwab fetch failed and the yfinance fallback is
    needed.
    """
    schwab_symbol = SCHWAB_DIRECT_INDEX.get(symbol, symbol)
    cache_key = (symbol, today_str)

    if cache_key in _CHAIN_CACHE:
        print(f"Reusing cached {schwab_symbol} chain")
        return _CHAIN_CACHE[cache_key]

    if cache_key in _SCHWAB_FETCH_FAILED:
        print(f"  Schwab chain fetch already failed this run — using {symbol} via yfinance")
        return None

    try:
        console.print()
        console.print(
            f"[bold italic grey42]Fetching {schwab_symbol} chain from Schwab[/bold italic grey42]"
        )

        raw = fetch_schwab_chain(schwab_symbol, today_str, max_dte)
        _CHAIN_CACHE[cache_key] = raw
        return raw

    except Exception as e:
        if is_direct_index:
            raise ValueError(
                f"Could not fetch {schwab_symbol} chain from Schwab ({e}) — "
                f"no fallback available for {symbol} (it has no ETF proxy)"
            )
        print(
            f"  Schwab chain fetch failed ({e}) — falling back to yfinance for {symbol}"
        )
        _SCHWAB_FETCH_FAILED.add(cache_key)
        return None


def get_spot(symbol, today_str):
    """Resolve spot for `symbol`, trying cache -> Schwab -> yfinance in that
    order. Independent of get_chain() — no shared state between the two
    beyond each having its own cache.

    Returns (spot, is_direct_index).
    """
    is_direct_index = symbol in SCHWAB_DIRECT_INDEX

    spot = _get_cached_or_schwab_spot(symbol, today_str, is_direct_index)
    if spot is None:
        spot = fetch_yfinance_spot(symbol)

    return spot, is_direct_index


def get_chain(symbol, today_str, max_dte, is_direct_index):
    """Resolve the raw chain for `symbol`, trying cache -> Schwab ->
    yfinance in that order. Independent of get_spot().

    Returns raw — a list of (exp_str, calls_df, puts_df) tuples — the same
    shape whether it came from Schwab or yfinance — ready to pass straight
    into collect_chain().
    """
    raw = _get_cached_or_schwab_chain(symbol, today_str, max_dte, is_direct_index)
    if raw is None:
        raw = fetch_yfinance_chain(symbol, today_str)

    return raw


def collect_chain(raw, spot, max_dte, dte_tau=None):
    """
    This is the second step where business logic filtering is applied to the data and the raw native format is converted
    to separate numpy arrays for more efficient transformation and calculation of the Black Scholes formulas

    Build DTE-weighted options arrays from already-resolved chain data (see
    get_chain() above for how `raw` is obtained).

    Returns (calls, puts, num_expirations) where each array is Nx4:
    [strike, weighted_OI, T_years, implied_vol]

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

    for exp_str, calls_df, puts_df in raw:
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


def get_risk_free_rate():
    """Live risk-free rate from SOFR (Fed FRED API), falling back to the
    configured default if the fetch fails.
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
        rf_rate_msg = (f"  {'Risk-Free Rate':<22}{RISK_FREE_RATE:.4f} (fallback — SOFR unavailable)")
        #console.print(f"  {'Risk-Free Rate':<22}{RISK_FREE_RATE:.4f} (fallback — SOFR unavailable)")
        return RISK_FREE_RATE, rf_rate_msg


def get_vol_close(symbol, is_direct_index, vix_ticker_override=None):
    """Fetch volatility index close (secondary reference field, not used in
    the math) — Schwab quote for direct-index symbols (SPX/NDX/VIX), or an
    explicit yfinance override ticker for anything else.

    Returns (vol_close, vol_ticker).
    """
    if is_direct_index:
        vol_ticker = SCHWAB_VOL_SYMBOL.get(symbol, "")
    else:
        vol_ticker = vix_ticker_override or ""

    if not vol_ticker:
        return 0.0, ""

    try:
        if is_direct_index:
            vol_close = fetch_schwab_quote_close(vol_ticker)
        else:
            vol_close = yf.Ticker(vol_ticker).fast_info["previousClose"]
        print(f"  {vol_ticker} previous close: {vol_close:.2f}")
        return vol_close, vol_ticker
    except Exception as e:
        print(f"  Warning: could not fetch {vol_ticker}: {e}")
        return 0.0, vol_ticker


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
