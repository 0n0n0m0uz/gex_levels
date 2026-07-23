
# Gex-Levels

Quickest way to run is with the shortcut below inside the project root directory
> uv run gex --flags

You can also specify the project root using this command:

> uv run --project ~/Github_Repos/gex-levels/ python -m gex_levels.main --your-args 
> 
> 
>  Old School Way OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")

## Schwab API

The Schwab API Access tokens are only valid for 7 days after which you must re-authenticate.

The below command will initiate the manual process which involves signing in via web-browser and a 2-factor code to email/phone
> uv run check_schwab_token

The script automatically handles the 30-minute refresh tokens and will keep updating the refresh tokens and storing them for the full 7-day access token lifetime.

--- 
Computes gamma exposure per strike using Black-Scholes (or Schwab's own
pre-computed greeks where used downstream), and derives key levels:
  - Gamma Flip: spot price where net dealer GEX crosses zero
  - Call Wall:  strike with highest call gamma concentration (resistance)
  - Put Wall:   strike with highest put gamma concentration (support)

Symbol routing — whatever you type is what gets fetched, no substitution:
  - SPX, NDX, VIX: real index option chain, fetched directly from Schwab
    (SCHWAB_DIRECT_INDEX). No ETF proxy, no ratio conversion — already in
    index space. VIX uses raw spot VIX as an approximation for the BS
    underlying price (Schwab has no futures data; see SCHWAB_DIRECT_INDEX
    comment for why the futures-basis-correct version isn't available).
  - Anything else (SPY, QQQ, AAPL, ...): that literal ticker's own chain,
    via Schwab first, yfinance fallback only for that same symbol. Manual
    --index/--vix ratio conversion is available as an opt-in for tickers
    with no native Schwab index chain (e.g. IWM -> ^RUT).

Improvements over naive GEX:
  - DTE-weighted OI (exp decay, tau=14d) — near-term gamma dominates
  - Skew-corrected gamma flip — IV shifts with hypothetical spot via
    empirical ATM skew slope (sticky-delta blend, alpha=0.5)
  - Hysteresis on walls — wall only moves if new candidate exceeds
    current wall's GEX by >10%, preventing day-to-day flip-flop

Writes key=value text files to data/ for the AMT GEX Levels ACSIL study
to fetch via raw.githubusercontent.com.

Usage:
    python gex_daily.py                    # SPX + NDX (default)
    python gex_daily.py SPX                # real \$SPX index chain
    python gex_daily.py VIX                # real \$VIX index chain
    python gex_daily.py SPY                # real SPY ETF chain (not converted)
    python gex_daily.py AAPL               # any stock, own price space
    python gex_daily.py IWM --index ^RUT   # manual ratio conversion
    python gex_daily.py SPX NDX VIX SPY    # multiple symbols

Dependencies: pip install yfinance numpy scipy requests

## 0DTE GEX

0DTE Gex requires normalization which divides the aggregate dollar gex by the spot price to remove the effect of the price level.
