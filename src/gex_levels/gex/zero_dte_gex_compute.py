from datetime import datetime, timezone
from typing import Optional, Union

from gex_levels.getData.fetch_spot import (
    get_spot,
    get_chain,
    get_risk_free_rate,
    get_index_ratio,
)
from gex_levels.gex.zero_dte_gex_calculations import (
    collect_chain_0dte,
    compute_per_strike_gex,
    compute_net_dex,
    compute_pcr,
    compute_hvl,
    compute_wall_zones,
    compute_vol_trigger,
    compute_skew_slope,
    compute_max_pain,
    find_gamma_flip,
    convert_to_index_space,
)
from gex_levels.outputs.rich_terminal_output import (
    print_dealer_positioning,
    print_volatility,
    print_gex_levels,
    print_gex_profile_and_hysteresis,
    print_footer,
)
from gex_levels.outputs.zero_dte_rich_terminal_output import print_market_data_0dte
from rich.console import Console

console = Console(force_terminal=True)

# Conservative estimate of the opening fraction of today's 0DTE volume (the
# rest is closings/rolls) — see collect_chain_0dte()'s docstring for why this
# is additive with OI rather than substitutive.
OPEN_RATIO = 0.35

####----------------------------------------------------------------------------------------------------------------####

def compute_gex_levels_0dte(
    symbol: str,
    index_ticker_override=None,
    no_index_conversion=False,
):
    """0DTE analogue of gex.gex_compute.compute_gex_levels() — same pipeline
    (get_spot -> get_chain -> per-strike GEX -> walls -> gamma flip -> optional
    index conversion), narrowed to just today's expiration.

    Differences from the daily pipeline, all driven by 0DTE having no future
    expirations to weight:
    - get_chain() is called with max_dte=0, so only today's expiration is
      fetched (not the full MAX_DTE breadth the daily path always pulls).
    - collect_chain_0dte() builds effective_OI = OI + volume * OPEN_RATIO
      instead of DTE-decay-weighted OI (there's no decay to weight on the
      last day), and uses a tighter ±15% OTM filter.
    - No wall hysteresis — 0DTE walls must be reactive, not sticky, so
      compute_wall_zones()'s raw zone is returned as-is (no
      apply_hysteresis/read_previous_etf_walls, unlike the daily version).
    - No historical chain snapshot: save_chain_snapshot() always writes to
      the single per-(symbol, date) Parquet file the daily path also writes;
      saving here with only today's single-expiration chain would silently
      overwrite that day's full-breadth daily snapshot (the same bug class
      already fixed once for the 30d/90d daily windows) — so 0DTE runs don't
      touch the historical store at all.

        index_ticker_override: yfinance ticker for manual ratio conversion,
                               for tickers with no native Schwab index chain
                               (e.g. '^RUT' for IWM). Ignored for SPX/NDX/VIX,
                               which are already in index space.
    """

    today_str = datetime.now().strftime("%Y-%m-%d")
    spot, is_direct_index = get_spot(symbol, today_str)
    # max_dte=0 — only fetch today's expiration, not the full MAX_DTE breadth.
    # Note: this shares the same (symbol, today_str) chain-cache key as the
    # daily path's own get_chain() calls, so within a single process running
    # both the 0DTE and daily pipelines for the same symbol/day would corrupt
    # each other's cached chain. main.py's --0dte branch is mutually exclusive
    # with the daily branch per invocation, so this doesn't currently happen.
    raw_chain = get_chain(symbol, today_str, 0, is_direct_index)
    risk_free_rate, rf_rate_msg = get_risk_free_rate()

    calls, puts, num_expirations = collect_chain_0dte(raw_chain, spot, OPEN_RATIO)

    if len(calls) == 0 and len(puts) == 0:
        raise ValueError(f"No 0DTE options data available for {symbol}")

#### --- Per-strike GEX (ticker price space) -----------------------------------------------------------------------####

    call_gex = compute_per_strike_gex(calls, spot, risk_free_rate, sign=+1.0)
    put_gex = compute_per_strike_gex(puts, spot, risk_free_rate, sign=-1.0)

    # --- Full GEX profile — all active strikes ---
    profile_by_strike = {}
    for s, v in call_gex.items():
        profile_by_strike[s] = profile_by_strike.get(s, 0.0) + v
    for s, v in put_gex.items():
        profile_by_strike[s] = profile_by_strike.get(s, 0.0) + v

    # --- Wall zones: 25%-75% cumulative GEX concentration bands, no hysteresis ---
    call_wall, call_wall_low, call_wall_high = compute_wall_zones(call_gex, spot, "call")
    put_wall, put_wall_low, put_wall_high = compute_wall_zones(put_gex, spot, "put")

    out_symbol = symbol

    # --- Net GEX and GEX regime ---
    net_gex = sum(call_gex.values()) + sum(put_gex.values())
    gex_regime = "positive_gamma" if net_gex >= 0 else "negative_gamma"

    # --- Net DEX and DEX regime ---
    net_dex, dex_regime = compute_net_dex(calls, puts, spot, risk_free_rate)
    dex_color = "red" if net_dex < 0 else "green"

    # --- Put/Call ratios ---
    pcr_raw, pcr_notional = compute_pcr(calls, puts)

    # --- HVL ---
    hvl = compute_hvl(call_gex, put_gex)

    # --- Max Pain ---
    max_pain = compute_max_pain(calls, puts)

    # --- Skew-corrected gamma flip ---
    skew_slope, skew_r2 = compute_skew_slope(calls, puts, spot)
    skew_alpha = 0.3 + 0.6 * skew_r2  # scales 0.3 (noisy fit) to 0.9 (clean fit)

    gamma_flip = find_gamma_flip(calls, puts, spot, skew_slope, skew_alpha, risk_free_rate)
    vol_trigger = compute_vol_trigger(call_gex, gamma_flip)

    # --- Optionally convert to index/futures price space ---
    # Direct-index fetches (SPX/NDX/VIX) are already in index space — no conversion.
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

####----Console output — reuses rich_terminal_output's styled functions directly where they're already generic (dealer positioning, volatility, GEX levels, footer); print_gex_profile_and_hysteresis() is fed neutral hysteresis values since 0DTE has none, and market data gets a 0DTE-specific variant (Open Ratio instead of Tau).----####

    print_market_data_0dte({
        "spot": spot, "rf_rate_msg": rf_rate_msg, "num_expirations": num_expirations,
        "calls": calls, "puts": puts, "open_ratio": OPEN_RATIO,
    })
    print_dealer_positioning({
        "dex_color": dex_color, "net_dex": net_dex, "dex_regime": dex_regime,
        "pcr_raw": pcr_raw, "pcr_notional": pcr_notional,
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
        "call_wall_held": False, "prev_cw": 0.0, "raw_call_wall": call_wall,
        "put_wall_held": False, "prev_pw": 0.0, "raw_put_wall": put_wall,
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
        "pcr_raw": float(pcr_raw),
        "pcr_notional": float(pcr_notional),
        "gex_profile": gex_profile,
    }
