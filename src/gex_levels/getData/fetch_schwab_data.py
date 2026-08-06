import os
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import pandas as pd


from gex_levels.config import BASE_DIR

from gex_levels.auth.api_auth_schwab import schwab_get

sys.path.append(str(BASE_DIR))

# Now this will work because the root is in sys.path
from debug.debug_hub import hub


def fetch_schwab_spot(schwab_symbol):
    """Live last price for `schwab_symbol` via Schwab's single-symbol quote
    endpoint (GET /{symbol}/quotes) — independent of the chains endpoint, no
    expiration-date lookup needed. Works for both direct-index symbols
    ($SPX, $NDX, $VIX) and literal equity/ETF tickers (SPY, AAPL, ...).
    """
    encoded = urllib.parse.quote(schwab_symbol, safe="")
    data = schwab_get(f"https://api.schwabapi.com/marketdata/v1/{encoded}/quotes", {})
    quote = (data.get(schwab_symbol) or {}).get("quote") or {}
    spot = quote.get("lastPrice")
    if not spot:
        raise ValueError(f"Schwab: no lastPrice for {schwab_symbol}")
    return float(spot)


_MAX_WORKERS = 5  # concurrency cap so a wide chain doesn't burst past Schwab's rate limit


def fetch_schwab_chain(schwab_symbol, today_str, max_dte):
    """Fetch an option chain from Schwab for any symbol — a direct index
    (e.g. $SPX, $NDX, $VIX) or a literal equity/ETF ticker (e.g. SPY, AAPL).
    Nothing about this function is index-specific; it just fetches whatever
    wire-format symbol it's given.

    A single chains request across the full date range with a wide strikeCount
    hits Schwab's gateway response-size limit ("Body buffer overflow") once
    there are enough expirations — and even near that limit, the strike range
    per expiration is far too narrow (needs ±20% OTM coverage). So instead:
    one cheap request to the dedicated expirationchain endpoint to enumerate
    expiration dates, then one full-breadth (range=ALL) chains request per
    expiration — each individually small enough to avoid the size limit, and
    each with the complete listed strike range for that expiration. The
    per-expiration requests are independent of each other, so they're fired
    concurrently (capped pool) instead of one at a time.

    Returns raw, matching fetch_yfinance_data.fetch_yfinance_chain's format: a list of
    (exp_str, calls_df, puts_df). For direct index symbols the strikes are
    already in index space (no ETF conversion needed). Spot is not returned
    here — see fetch_schwab_spot() for that.
    """

    enum_data = schwab_get(
        "https://api.schwabapi.com/marketdata/v1/expirationchain",
        {"symbol": schwab_symbol},
    )

    exp_dates = sorted(
        item["expirationDate"]
        for item in enum_data.get("expirationList", [])
        if item["expirationDate"] >= today_str and item["daysToExpiration"] <= max_dte
    )

    def _fetch_one(exp_date):
        exp_data = schwab_get(
            "https://api.schwabapi.com/marketdata/v1/chains",
            {
                "symbol": schwab_symbol,
                "fromDate": exp_date,
                "toDate": exp_date,
                "range": "ALL",
            },
        )
        return _parse_chain_response(exp_data)

    by_exp = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        for parsed in pool.map(_fetch_one, exp_dates):
            by_exp.update(parsed)

    raw = [
        (exp, pd.DataFrame(v["call"]), pd.DataFrame(v["put"]))
        for exp, v in sorted(by_exp.items())
        if v["call"] and v["put"]
    ]
    return raw


def _parse_chain_response(data):
    """Flatten one Schwab chains response into {exp_str: {"call": [...], "put": [...]}}."""
    by_exp = {}
    for map_key, opt_type in [("callExpDateMap", "call"), ("putExpDateMap", "put")]:
        for exp_key, strikes in data.get(map_key, {}).items():
            exp_str = exp_key.split(":")[0]
            by_exp.setdefault(exp_str, {"call": [], "put": []})
            for contracts in strikes.values():
                for opt in contracts:
                    by_exp[exp_str][opt_type].append(
                        {
                            "strike": float(opt.get("strikePrice", 0)),
                            "openInterest": int(opt.get("openInterest") or 0),
                            "totalVolume": int(opt.get("totalVolume") or 0),
                            "impliedVolatility": float(opt.get("volatility") or 0)
                            / 100.0,
                        }
                    )
    return by_exp