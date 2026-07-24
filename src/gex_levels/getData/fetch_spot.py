# Checks cache for previously existing data, if it doesnt exist fetches spot price and spot interest rates from schwab or yfinance


import requests
import yfinance as yf

from rich.console import Console

from gex_levels.config import (
    RISK_FREE_RATE,
    SCHWAB_DIRECT_INDEX,
    _CHAIN_CACHE,
    _SCHWAB_SPOT_CACHE,
    _SCHWAB_FETCH_FAILED,
)
from gex_levels.getData.fetch_schwab_data import fetch_schwab_chain

console = Console(force_terminal=True)


def _get_cached_or_schwab_spot(symbol, today_str, max_dte, is_direct_index):
    """Try the shared chain cache, then Schwab. Populates _CHAIN_CACHE /
    _SCHWAB_SPOT_CACHE on a fresh fetch. Returns (spot, raw), or (None, None)
    if Schwab fetch failed and the yfinance fallback is needed.
    """
    schwab_symbol = SCHWAB_DIRECT_INDEX.get(symbol, symbol)
    cache_key = (symbol, today_str)

    if cache_key in _CHAIN_CACHE and cache_key in _SCHWAB_SPOT_CACHE:
        # Reuse the same chain+spot snapshot across the 30d/90d passes —
        # avoids a second Schwab call and keeps both windows consistent.
        spot = _SCHWAB_SPOT_CACHE[cache_key]
        print(f"Reusing cached {schwab_symbol} chain — spot: {spot:.2f}")
        return spot, _CHAIN_CACHE[cache_key]

    if cache_key in _SCHWAB_FETCH_FAILED:
        print(f"  Schwab fetch already failed this run — using {symbol} via yfinance")
        return None, None

    try:
        console.print()
        console.print(
            f"[bold italic grey42]Fetching {schwab_symbol} from Schwab[/bold italic grey42]"
        )

        spot, raw = fetch_schwab_chain(schwab_symbol, today_str, max_dte)
        if raw is None:
            raise ValueError("Schwab FAILED TO RETURN an option chain")

        _CHAIN_CACHE[cache_key] = raw
        _SCHWAB_SPOT_CACHE[cache_key] = spot
        return spot, raw

    except Exception as e:
        if is_direct_index:
            # No ETF proxy exists for a pure index under this design —
            # falling back would mean silently substituting a different
            # symbol, which is exactly what we're trying not to do.
            raise ValueError(
                f"Could not fetch {schwab_symbol} from Schwab ({e}) — "
                f"no fallback available for {symbol} (it has no ETF proxy)"
            )
        print(
            f"  Schwab fetch failed ({e}) — falling back to yfinance for {symbol}"
        )
        _SCHWAB_FETCH_FAILED.add(cache_key)
        return None, None


def _get_yfinance_spot(symbol):
    """yfinance spot-only fallback — only reachable for non-index symbols
    (SPY, QQQ, stocks). The chain itself is fetched separately via
    _download_options().
    """
    print(f"  Fetching {symbol} price + options chain via yfinance...")
    ticker = yf.Ticker(symbol)

    # Fresh spot via 1m bar — fast_info["lastPrice"] lags during the session
    spot = None
    try:
        hist = ticker.history(period="1d", interval="1m")
        if not hist.empty:
            spot = float(hist["Close"].iloc[-1])
    except Exception:
        pass
    if not spot or spot <= 0:
        try:
            spot = ticker.fast_info["lastPrice"]
        except Exception:
            spot = ticker.info.get("regularMarketPrice") or ticker.info.get(
                "previousClose"
            )
    if not spot or spot <= 0:
        raise ValueError(f"Could not get price for {symbol}")

    return spot, ticker


def _download_options(ticker, symbol, today_str):
    """yfinance chain download, used only for the fallback path (Schwab-sourced
    chains are already fetched by _get_cached_or_schwab_spot)."""
    key = (symbol, today_str)
    if key in _CHAIN_CACHE:
        return _CHAIN_CACHE[key]

    raw = []
    for exp_str in ticker.options:
        try:
            chain = ticker.option_chain(exp_str)
            raw.append((exp_str, chain.calls, chain.puts))
        except Exception as e:
            print(f"    Skip {exp_str}: {e}")

    _CHAIN_CACHE[key] = raw
    return raw


def get_spot_and_chain(symbol, today_str, max_dte):
    """Resolve spot and raw chain for `symbol`, trying cache -> Schwab ->
    yfinance in that order.

    Returns (spot, raw, is_direct_index). `raw` is a list of
    (exp_str, calls_df, puts_df) tuples — the same shape whether it came
    from Schwab or yfinance — ready to pass straight into collect_chain().
    """
    is_direct_index = symbol in SCHWAB_DIRECT_INDEX

    spot, raw = _get_cached_or_schwab_spot(symbol, today_str, max_dte, is_direct_index)

    if spot is None:
        spot, ticker = _get_yfinance_spot(symbol)
        raw = _download_options(ticker, symbol, today_str)

    return spot, raw, is_direct_index


def get_risk_free_rate():
    """Live risk-free rate from SOFR (Fed FRED API), falling back to the
    configured default if the fetch fails.
    """
    try:
        r = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR", timeout=10
        )
        sofr = float(r.text.strip().split("\n")[-1].split(",")[1]) / 100
        console.print(f"  {'Risk-Free Rate':<22} {sofr:.2%} (SOFR)")
        return sofr
    except Exception:
        console.print(
            f"  {'Risk-Free Rate':<22}{RISK_FREE_RATE:.4f} (fallback — SOFR unavailable)"
        )
        return RISK_FREE_RATE
