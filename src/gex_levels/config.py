# Directory
from gex_levels.utils.paths import get_project_root

BASE_DIR = get_project_root()
OUTPUT_DIR = BASE_DIR / "data"


# Default symbols when none are given on the command line
DEFAULT_SYMBOLS = ["SPX", "NDX"]

# Per-session chain cache: (symbol, date_str) -> list of (exp_str, calls_df, puts_df)
# Avoids re-downloading the full chain when computing both 30d and 90d windows.
_CHAIN_CACHE = {}
# Per-session spot cache for the Schwab fetch path, keyed the same way as _CHAIN_CACHE.
_SCHWAB_SPOT_CACHE = {}
# (symbol, date_str) keys where the Schwab fetch already failed this run — once one
# window falls back to yfinance, every other window for the same symbol/day falls
# back too, so the 30d/90d pair never ends up sourced from two different chains.
_SCHWAB_FETCH_FAILED = set()

# This is a hard cutoff on future expiration. The script will not even consider any expirations beyond.
MAX_DTE = 90  # include up to 90 DTE (weighted down by decay)

# These are mathematical constants used as decay rates in terms of weighting the importance of future expirations.
# On a 30-day approach 7 / 30 is a faster decay than the 90-day approach -- on a 90-day approach
# options 3 weeks out are relatively more important than on a 30-day approach where they are closer to expiration
DTE_TAU_30 = 7.0  # 30d window: aggressive near-term focus — weekly gamma dominates
DTE_TAU_90 = 30.0  # 90d window: monthly/quarterly positioning registers meaningfully

# Secured Overnight Financing Rate
# SOFR — Secured Overnight Financing Rate. It's the rate at which banks borrow cash overnight using U.S. Treasury securities as collateral.
# It replaced LIBOR in 2023 as the standard benchmark risk-free rate in the U.S. financial system and is published daily by the New York Fed.
# https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR
RISK_FREE_RATE = 0.035

# Volatility SKEW
# Depending on the symbol, the correlation between price and IV is different. For MEME stocks for example, the higher price climbs,
# IV will rise with it since they assume an equally hard reversal crash.
# For index options the opposite is true, IV tends to fall as price steadily climbs in a good macro environment.
# .65 - .75 may be more accurate for SPX according to J.P. Morgan.
SKEW_ALPHA = 0.5  # blend: 0=sticky strike, 1=sticky delta. .5 is a middle ground, partial correlation.

# Turned off. Acts like a buffer only changing the call wall vs yesterday if GEX changes by 10% or more.
# The idea was to eliminate meaningless noise and have a stable level to trade around over the swing period.
WALL_HYSTERESIS = 0.00  # 10% — wall only moves if new candidate is 10%+ stronger

# Symbols with a real, direct Schwab index chain (no ETF proxy needed at all).
# Keyed by exactly what you type: enter "SPX" and you get $SPX; enter "SPY"
# and you get real SPY (see compute_gex_levels) — no silent substitution
# between the two in either direction.
#
# VIX note: real VIX options price off the corresponding VIX future, not spot
# VIX. Schwab's API has no futures data (verified — no ticker convention for
# /VX futures returns anything), and yfinance futures data was already tried
# and removed elsewhere in this project for unreliability (wrong contract near
# rollover). So VIX gamma here uses raw spot VIX as an approximation — flag
# this if VIX levels look off during steep contango/backwardation.
SCHWAB_DIRECT_INDEX = {"SPX": "$SPX", "NDX": "$NDX", "VIX": "$VIX"}

# Secondary vol-index close reported alongside SPX/NDX runs (not a primary symbol)
SCHWAB_VOL_SYMBOL = {"SPX": "$VIX", "NDX": "$VXN"}
