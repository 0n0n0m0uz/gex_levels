from gex_levels.config import (
    MAX_DTE,
    DTE_TAU_30,
    DTE_TAU_90,
)
from gex_levels.getData.fetch_spot import (
    get_spot,
    get_chain,
    collect_chain,
    get_risk_free_rate,
    get_index_ratio,
)
from gex_levels.gex.gex_calculations import (
    compute_per_strike_gex,
    compute_net_dex,
    compute_cpr,
    compute_hvl,
    compute_wall_zones,
    compute_vol_trigger,
    compute_skew_slope,
    compute_max_pain,
    find_gamma_flip,
    read_previous_etf_walls,
    apply_hysteresis,
    convert_to_index_space,
)
from gex_levels.outputs.rich_terminal_output import (
    print_market_data,
    print_dealer_positioning,
    print_volatility,
    print_gex_levels,
    print_gex_profile_and_hysteresis,
    print_footer,
)
from gex_levels.outputs.historical_store import save_chain_snapshot
from debug.debug_hub import hub

####--------------------------------------------------------------------------------------------------------------######

import os
import sys
from datetime import datetime, timezone
####----------------------------------------------------------------------------------------------------------------####
from typing import Optional, Union
from rich.console import Console
# Adds colors and formats terminal output
# May Want to Change because this could throw error for someone without color compatible terminal
console = Console(force_terminal=True)

####----------------------------------------------------------------------------------------------------------------####

def compute_gex_levels(
    symbol: str,
    max_dte=MAX_DTE,
    index_ticker_override=None,
    no_index_conversion=False,):

    """The primary orchestrator module initiated by  main.py

    It's the pipeline to calculate GEX for the symbol passed.

        index_ticker_override: yfinance ticker for manual ratio conversion, for
                               tickers with no native Schwab index chain
                               (e.g. '^RUT' for IWM). Ignored for SPX/NDX/VIX,
                               which are already in index space.
    """

    ####### Basic Setup of Symbol along with spot price ------------------------------------------------------------####

    # symbol = symbol.upper()
    today_str = datetime.now().strftime("%Y-%m-%d")
    # is_direct_index is needed because yfinance doesnt use the same $SPX format as Schwab requires
    spot, is_direct_index = get_spot(symbol, today_str)
    # Always fetch at the full MAX_DTE breadth (not this call's own max_dte) so the
    # historical chain snapshot below is always complete regardless of which --days
    # window(s) get requested, or in what order across separate same-day runs.
    # collect_chain() below still correctly narrows to this window's own max_dte.
    raw_chain = get_chain(symbol, today_str, MAX_DTE, is_direct_index)
    # get_chain has the logic to get the chain from either schwab or yfinance
    save_chain_snapshot(symbol, today_str, raw_chain)
    #### Fetch live risk-free rate from SOFR (Fed FRED API)
    risk_free_rate, rf_rate_msg = get_risk_free_rate()
    ####  Raw Data is Downloaded, filtered according to Business Logic and then separated into Numpy Arrays for more efficient processing ####################################################################################################################################
    tau = DTE_TAU_30 if max_dte <= 30 else DTE_TAU_90

    # collect_chain is the transformation of the raw api data into the format needed for futher processing
    calls, puts, num_expirations = collect_chain(raw_chain, spot, max_dte, dte_tau=tau)

    if len(calls) == 0 and len(puts) == 0:
        raise ValueError(f"No options data available for {symbol}")

#### --- Per-strike GEX (ticker price space) -----------------------------------------------------------------------####

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
    tenor = "30" if max_dte <= 30 else "90"
    prev_cw, prev_pw = read_previous_etf_walls(symbol, out_symbol, tenor)
    call_wall = apply_hysteresis(call_gex, raw_call_wall, prev_cw)
    put_wall = apply_hysteresis(put_gex, raw_put_wall, prev_pw)

    # Ticker-space walls, captured before any index conversion below reassigns
    # call_wall/put_wall — the hysteresis check further down runs after that
    # conversion (for print-ordering reasons), so it needs its own ticker-space
    # copies to compare against raw_call_wall/raw_put_wall (also ticker-space).
    ticker_call_wall = call_wall
    ticker_put_wall = put_wall

    # Hysteresis: a held wall keeps its previous zone (single point, not a
    # range) — this reassignment must stay here since it feeds the return
    # dict below, unlike everything the print_* calls below report.
    call_wall_held = ticker_call_wall != raw_call_wall
    put_wall_held = ticker_put_wall != raw_put_wall
    if call_wall_held:
        call_wall_low = call_wall_high = ticker_call_wall
    if put_wall_held:
        put_wall_low = put_wall_high = ticker_put_wall

    # --- Net GEX and GEX regime ---
    net_gex = sum(call_gex.values()) + sum(put_gex.values())
    gex_regime = "positive_gamma" if net_gex >= 0 else "negative_gamma"

    # --- Net DEX and DEX regime ---
    net_dex, dex_regime = compute_net_dex(calls, puts, spot, risk_free_rate)
    dex_color = "red" if net_dex < 0 else "green"

    # --- Call/Put ratios ---
    cpr_raw, cpr_notional = compute_cpr(calls, puts)

    # --- HVL and Vol Trigger (ticker price space) ---
    hvl = compute_hvl(call_gex, put_gex)

    # --- Max Pain ---
    max_pain = compute_max_pain(calls, puts)

    # --- Vol Trigger ---
    vol_trigger = compute_vol_trigger(
        call_gex, gamma_flip=0.0
    )  # placeholder; recomputed below

    # This line can be changes to easily swap between a hardcoded alpha_skew and one calculated based on the options chain
    skew_slope, skew_r2 = compute_skew_slope(calls, puts, spot)
    skew_alpha = 0.3 + 0.6 * skew_r2  # scales 0.3 (noisy fit) to 0.9 (clean fit)
    # skew_alpha = 0.7

    #print(f"  Computing gamma flip...")
    # --- Skew-corrected gamma flip ---
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
            fetched_ratio, index_price = get_index_ratio(index_ticker, spot, symbol)
            if fetched_ratio is not None:
                ratio = fetched_ratio
                gamma_flip, call_wall, put_wall, hvl, vol_trigger, max_pain, net_dex = (
                    convert_to_index_space(
                        ratio, gamma_flip, call_wall, put_wall, hvl, vol_trigger, max_pain, net_dex
                    )
                )
                spot = index_price
        else:
            console.print(
                f"[bold italic grey42]No index conversion requested — levels stay in {symbol} price space[/bold italic grey42]"
            )

    # Convert profile strikes to output price space
    gex_profile = sorted(
        [(round(s * ratio), int(profile_by_strike[s])) for s in profile_by_strike],
        key=lambda p: p[0],
    )

####----Console output moved to outputs/rich_terminal_output.py — this only computes.----####

    print_market_data({
        "spot": spot, "rf_rate_msg": rf_rate_msg, "num_expirations": num_expirations,
        "calls": calls, "puts": puts, "tau": tau,
    })
    print_dealer_positioning({
        "dex_color": dex_color, "net_dex": net_dex, "dex_regime": dex_regime,
        "cpr_raw": cpr_raw, "cpr_notional": cpr_notional,
    })
    print_volatility({
        "skew_slope": skew_slope, "skew_r2": skew_r2, "skew_alpha": skew_alpha,
    })
    print_gex_levels({
        "gamma_flip": gamma_flip, "call_wall": call_wall, "put_wall": put_wall,
        "hvl": hvl, "vol_trigger": vol_trigger, "max_pain": max_pain,
    })
    print_gex_profile_and_hysteresis({
        "gex_profile": gex_profile,
        "call_wall_held": call_wall_held, "prev_cw": prev_cw, "raw_call_wall": raw_call_wall,
        "put_wall_held": put_wall_held, "prev_pw": prev_pw, "raw_put_wall": raw_put_wall,
    })
    print_footer()

####---------------------------------------------------------------------------------------------####

    return {
        "symbol": out_symbol,
        "underlying": float(spot),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gex_regime": gex_regime,
        "gamma_flip": float(gamma_flip),
        "vol_trigger": float(vol_trigger),
        "hvl": float(hvl),
        "max_pain": float(max_pain),
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
        "cpr_notional": float(cpr_notional),
        "etf_gamma_flip": etf_gamma_flip,
        "etf_call_wall": etf_call_wall,
        "etf_put_wall": etf_put_wall,
        "gex_profile": gex_profile,
    }

