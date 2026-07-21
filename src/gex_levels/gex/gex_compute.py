import os
import sys
from datetime import datetime, timezone
from typing import Optional, Union

import yfinance as yf


from gex_levels.config import (
    MAX_DTE,
    DTE_TAU_30,
    DTE_TAU_90,
    RISK_FREE_RATE,
    SCHWAB_DIRECT_INDEX,
    SCHWAB_VOL_SYMBOL,
    _CHAIN_CACHE,
    _SCHWAB_SPOT_CACHE,
    _SCHWAB_FETCH_FAILED,
)
from gex_levels.getData.fetch_schwab_data import (
    fetch_schwab_chain,
    fetch_schwab_quote_close,
)
from gex_levels.getData.fetch_yfinance_data import collect_chain
from gex_levels.gex.gex_calculations import (
    compute_per_strike_gex,
    compute_net_dex,
    compute_cpr,
    compute_hvl,
    compute_wall_zones,
    compute_vol_trigger,
    compute_skew_slope,
    find_gamma_flip,
    read_previous_etf_walls,
    apply_hysteresis,
)
from debug.debug_hub import hub

def compute_gex_levels(
    symbol,
    max_dte=MAX_DTE,
    index_ticker_override=None,
    vix_ticker_override=None,
    no_index_conversion=False,
):
    """Full GEX computation for one symbol.

    Whatever you pass as `symbol` is what gets fetched — SPX/NDX/VIX fetch the
    real index chain directly from Schwab; any other ticker (SPY, QQQ, AAPL,
    ...) fetches that literal ticker's own chain via Schwab, falling back to
    yfinance only for that same symbol (never substituting a different one).

    index_ticker_override: yfinance ticker for manual ratio conversion, for
                           tickers with no native Schwab index chain
                           (e.g. '^RUT' for IWM). Ignored for SPX/NDX/VIX,
                           which are already in index space.
    vix_ticker_override:   yfinance ticker for vol index close (e.g. '^RVX'),
                           manual opt-in for non-index symbols.
    """
    ####### Basic Setup of Symbol along with spot price #######################################################################################################################################
    symbol = symbol.upper()


    today_str = datetime.now().strftime("%Y-%m-%d")


    is_direct_index = symbol in SCHWAB_DIRECT_INDEX # T/F would be T if nothing passed to command line, and F is regular stock is passed

    schwab_symbol = SCHWAB_DIRECT_INDEX.get(symbol, symbol)
    cache_key = (symbol, today_str)

    ticker = None
    spot = None

    if cache_key in _CHAIN_CACHE and cache_key in _SCHWAB_SPOT_CACHE:
        # Reuse the same chain+spot snapshot across the 30d/90d passes —
        # avoids a second Schwab call and keeps both windows consistent.
        spot = _SCHWAB_SPOT_CACHE[cache_key]
        print(f"  Reusing cached {schwab_symbol} chain — spot: {spot:.2f}")
    elif cache_key in _SCHWAB_FETCH_FAILED:
        print(f"  Schwab fetch already failed this run — using {symbol} via yfinance")
    else:
        try:
            print(f"  Fetching {schwab_symbol} from Schwab...") ## Next Line that Prints is 130 below
            spot, raw = fetch_schwab_chain(schwab_symbol, today_str, max_dte)
            if raw is None:
                raise ValueError("Schwab FAILED TO RETURN an option chain")

            _CHAIN_CACHE[cache_key] = raw
            _SCHWAB_SPOT_CACHE[cache_key] = spot

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

    if spot is None:
        # yfinance fallback — only reachable for non-index symbols (SPY, QQQ, stocks)
        print(f"  Fetching {symbol} price + options chain via yfinance...")
        ticker = yf.Ticker(symbol)

        # Fresh spot via 1m bar — fast_info["lastPrice"] lags during the session
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
        print(f"  Spot: ${spot:.2f}")

    #### Fetch live risk-free rate from SOFR (Fed FRED API)  ########################################################################################
    try:
        import requests

        r = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR", timeout=10
        )
        sofr = float(r.text.strip().split("\n")[-1].split(",")[1]) / 100
        risk_free_rate = sofr
        print(f"  Risk-free rate: {risk_free_rate:.4f} (SOFR)")
    except Exception:
        risk_free_rate = RISK_FREE_RATE
        print(f"  Risk-free rate: {risk_free_rate:.4f} (fallback — SOFR unavailable)")

    ####  Raw Data is Downloaded, filtered according to Business Logic and then separated into Numpy Arrays for more efficient processing ####################################################################################################################################
    tau = DTE_TAU_30 if max_dte <= 30 else DTE_TAU_90

    # ticker is None when the Schwab path already succeeded — collect_chain still
    # works because _download_options() checks _CHAIN_CACHE (already populated by
    # fetch_schwab_chain above) before ever touching ticker. yfinance's Ticker.options
    # is only reached on a cache miss, i.e. when Schwab failed and ticker is real.
    calls, puts, exp_count = collect_chain(
        ticker, spot, max_dte, symbol, today_str, dte_tau=tau
    )

    print(
        f"  {exp_count} expirations, {len(calls)} calls, {len(puts)} puts  (tau={tau:.0f}d)"
    )

    if len(calls) == 0 and len(puts) == 0:
        raise ValueError(f"No options data for {symbol}")

    ##### --- Per-strike GEX (ticker price space) --- ##############################################################################################
    call_gex = compute_per_strike_gex(calls, spot, risk_free_rate, sign=+1.0)
    put_gex = compute_per_strike_gex(puts, spot, risk_free_rate, sign=-1.0)

    # --- Full GEX profile — all active strikes (not just top N) ---
    profile_by_strike = {}
    for s, v in call_gex.items():
        profile_by_strike[s] = profile_by_strike.get(s, 0.0) + v
    for s, v in put_gex.items():
        profile_by_strike[s] = profile_by_strike.get(s, 0.0) + v

    # --- Wall zones: 25%-75% cumulative GEX concentration bands ---
    raw_call_wall, call_wall_low, call_wall_high = compute_wall_zones(
        call_gex, spot, "call"
    )
    raw_put_wall, put_wall_low, put_wall_high = compute_wall_zones(put_gex, spot, "put")

    # Output symbol is just the literal symbol now — no more relabeling
    out_symbol = symbol

    # Hysteresis on the wall strike itself
    prev_cw, prev_pw = read_previous_etf_walls(symbol, out_symbol)
    call_wall = apply_hysteresis(call_gex, raw_call_wall, prev_cw)
    put_wall = apply_hysteresis(put_gex, raw_put_wall, prev_pw)

    if call_wall != raw_call_wall:
        print(
            f"  Call wall held at {prev_cw:.2f} (hysteresis — new candidate {raw_call_wall:.2f} not 10%+ stronger)"
        )
        call_wall_low = call_wall_high = call_wall  # single held point, no zone
    if put_wall != raw_put_wall:
        print(
            f"  Put wall held at {prev_pw:.2f} (hysteresis — new candidate {raw_put_wall:.2f} not 10%+ stronger)"
        )
        put_wall_low = put_wall_high = put_wall

    # Net GEX and regime
    net_gex = sum(call_gex.values()) + sum(put_gex.values())
    regime = "positive_gamma" if net_gex >= 0 else "negative_gamma"

    # --- Net DEX and DEX regime ---
    net_dex, dex_regime = compute_net_dex(calls, puts, spot, risk_free_rate)
    print(f"  Net DEX: {net_dex:,.0f} ({dex_regime})")

    # --- Call/Put ratios ---
    cpr_raw, cpr_notl = compute_cpr(calls, puts)
    print(f"  CPR raw: {cpr_raw:.4f}  CPR notional: {cpr_notl:.4f}")

    # --- HVL and Vol Trigger (ticker price space) ---
    hvl = compute_hvl(call_gex, put_gex)
    vol_trigger = compute_vol_trigger(
        call_gex, gamma_flip=0.0
    )  # placeholder; recomputed below

    # --- Skew-corrected gamma flip ---
    # This line can be changes to easily swap between a hardcoded alpha_skew and one calculated based on the options chain
    skew_slope, skew_r2 = compute_skew_slope(calls, puts, spot)
    skew_alpha = 0.3 + 0.6 * skew_r2  # scales 0.3 (noisy fit) to 0.9 (clean fit)
    # skew_alpha = 0.7
    print(
        f"  ATM skew slope: {skew_slope:.6f}  R²: {skew_r2:.3f}  alpha: {skew_alpha:.2f}"
    )
    print(f"  Computing gamma flip...")

    gamma_flip = find_gamma_flip(
        calls, puts, spot, skew_slope, skew_alpha, risk_free_rate
    )

    vol_trigger = compute_vol_trigger(call_gex, gamma_flip)

    # Save ticker-space walls for next run's hysteresis comparison
    etf_call_wall = float(call_wall)
    etf_put_wall = float(put_wall)
    etf_gamma_flip = float(gamma_flip)

    # --- Optionally convert to index/futures price space ---
    # Direct-index fetches (SPX/NDX/VIX) are already in index space — no conversion.
    # For everything else, conversion only happens if explicitly requested via
    # --index (e.g. IWM -> ^RUT) — there is no automatic built-in default anymore.
    ratio = 1.0
    if is_direct_index:
        print(
            f"  Direct index fetch — already in {out_symbol} space, no ETF ratio conversion"
        )
    else:
        index_ticker: Optional[Union[str, tuple[str, str]]] = (
            None if no_index_conversion else index_ticker_override
        )
        if index_ticker is not None and isinstance(index_ticker, (str, tuple)):
            try:
                idx = yf.Ticker(index_ticker)
                index_price = idx.fast_info["lastPrice"]
                ratio = index_price / spot
                print(f"  Index {index_ticker}: {index_price:.2f} (ratio {ratio:.2f}x)")
                gamma_flip *= ratio
                call_wall *= ratio
                put_wall *= ratio
                hvl *= ratio
                vol_trigger *= ratio
                net_dex *= ratio
                spot = index_price
            except Exception as e:
                print(
                    f"  Warning: could not fetch {index_ticker}, levels stay in {symbol} price space: {e}"
                )
        else:
            print(
                f"  No index conversion requested — levels stay in {symbol} price space"
            )

    print(f"  HVL: {hvl:.2f}  Vol Trigger: {vol_trigger:.2f}")

    # Convert profile strikes to output price space
    gex_profile = sorted(
        [(round(s * ratio), int(profile_by_strike[s])) for s in profile_by_strike],
        key=lambda p: p[0],
    )
    print(
        f"  GEX profile: {len(gex_profile)} strikes ({sum(1 for _, g in gex_profile if g > 0)} call, {sum(1 for _, g in gex_profile if g < 0)} put)"
    )
    # Prints two blank lines of space to terminal to separate the 30d and 90d data
    print("\n\n")


    # --- Fetch volatility index close (secondary reference field, not used in the math) ---
    vol_close = 0.0
    if is_direct_index:
        vol_ticker = SCHWAB_VOL_SYMBOL.get(symbol, "")
        if vol_ticker:
            try:
                vol_close = fetch_schwab_quote_close(vol_ticker)
                print(f"  {vol_ticker} previous close: {vol_close:.2f}")
            except Exception as e:
                print(f"  Warning: could not fetch {vol_ticker}: {e}")
    else:
        vol_ticker = vix_ticker_override or ""
        if vol_ticker:
            try:
                vt = yf.Ticker(vol_ticker)
                vol_close = vt.fast_info["previousClose"]
                print(f"  {vol_ticker} previous close: {vol_close:.2f}")
            except Exception as e:
                print(f"  Warning: could not fetch {vol_ticker}: {e}")

    return {
        "symbol": out_symbol,
        "underlying": float(spot),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regime": regime,
        "gamma_flip": float(gamma_flip),
        "vol_trigger": float(vol_trigger),
        "hvl": float(hvl),
        "call_wall": float(call_wall),
        "call_wall_low": float(call_wall_low * ratio),
        "call_wall_high": float(call_wall_high * ratio),
        "put_wall": float(put_wall),
        "put_wall_low": float(put_wall_low * ratio),
        "put_wall_high": float(put_wall_high * ratio),
        "net_gex": float(net_gex),
        "net_dex": float(net_dex),
        "dex_regime": dex_regime,
        "cpr_raw": float(cpr_raw),
        "cpr_notl": float(cpr_notl),
        "etf_gamma_flip": etf_gamma_flip,
        "etf_call_wall": etf_call_wall,
        "etf_put_wall": etf_put_wall,
        "vol_close": float(vol_close),
        "vol_ticker": vol_ticker or "",
        "gex_profile": gex_profile,
    }

