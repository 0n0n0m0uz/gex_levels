import yfinance as yf

from gex_levels.config import _CHAIN_CACHE


def fetch_yfinance_spot(symbol):
    """Live spot price for `symbol` via yfinance — only reachable for
    non-index symbols (SPY, QQQ, stocks), used as the fallback when Schwab's
    spot fetch fails. The chain itself is fetched separately via
    fetch_yfinance_chain().
    """
    print(f"  Fetching {symbol} price via yfinance...")
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

    return spot


def fetch_yfinance_chain(symbol, today_str):
    """Option chain for `symbol` via yfinance, used only for the fallback
    path when Schwab's chain fetch fails (see fetch_spot.py's
    _get_cached_or_schwab_chain). Returns raw: a list of
    (exp_str, calls_df, puts_df) tuples — the same shape as
    fetch_schwab_data.fetch_schwab_chain's output.
    """
    key = (symbol, today_str)
    if key in _CHAIN_CACHE:
        return _CHAIN_CACHE[key]

    ticker = yf.Ticker(symbol)
    raw = []
    for exp_str in ticker.options:
        try:
            chain = ticker.option_chain(exp_str)
            raw.append((exp_str, chain.calls, chain.puts))
        except Exception as e:
            print(f"    Skip {exp_str}: {e}")

    _CHAIN_CACHE[key] = raw
    return raw