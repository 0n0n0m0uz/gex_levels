import os
import sys
from datetime import datetime, timezone
from typing import Optional, Union

import yfinance as yf

from rich.console import Console
from rich.rule import Rule

# May Want to Change because this could throw error for someone without color compatible terminal
console = Console(force_terminal=True)

from gex_levels.config import (
    MAX_DTE,
    DTE_TAU_30,
    DTE_TAU_90,
    SCHWAB_VOL_SYMBOL,
)
from gex_levels.getData.fetch_spot import get_spot_and_chain, get_risk_free_rate
from gex_levels.getData.fetch_schwab_data import fetch_schwab_quote_close
from gex_levels.getData.fetch_yfinance_data import collect_chain
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

    spot, raw, is_direct_index = get_spot_and_chain(symbol, today_str, max_dte)
##################################################################
    console.print(Rule("[bold green]Market Data[/bold green]"))
    console.print()
    console.print(f"  {'Spot':<22} ${spot:.2f}")
#####################################################################

    #### Fetch live risk-free rate from SOFR (Fed FRED API)  ########################################################################################
    risk_free_rate = get_risk_free_rate()

    ####  Raw Data is Downloaded, filtered according to Business Logic and then separated into Numpy Arrays for more efficient processing ####################################################################################################################################
    tau = DTE_TAU_30 if max_dte <= 30 else DTE_TAU_90

    calls, puts, exp_count = collect_chain(raw, spot, max_dte, dte_tau=tau)
##########################################################################
    console.print(f"  {'Expirations':<22} {exp_count}")
    console.print(f"  {'Calls':<22} {len(calls):,}")
    console.print(f"  {'Puts':<22} {len(puts):,}")
    console.print(f"  {'Tau':<22} {tau:.0f}-days")
###########################################################################


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

    console.print(Rule("[bold magenta]Dealer Positioning[/bold magenta]"))
    console.print()

    # Net GEX and regime
    net_gex = sum(call_gex.values()) + sum(put_gex.values())
    regime = "positive_gamma" if net_gex >= 0 else "negative_gamma"

    # --- Net DEX and DEX regime ---
    # net_gex, regime = compute_net_gex(calls, puts, spot, risk_free_rate)
    # gex_color = "red" if net_gex < 0 else "green"
    #
    # console.print(
    #     f"  {'Net GEX':<22}"
    #     f"[{gex_color}]${net_gex:,.0f}[/{gex_color}] "
    #     f"({gex_regime})"
    # )


    # --- Net DEX and DEX regime ---
    net_dex, dex_regime = compute_net_dex(calls, puts, spot, risk_free_rate)
    dex_color = "red" if net_dex < 0 else "green"

    # --- Call/Put ratios ---
    cpr_raw, cpr_notional = compute_cpr(calls, puts)

##########################################################################

    console.print(
        f"  {'Net DEX':<22} "
        f"[{dex_color}]${net_dex:,.0f}[/{dex_color}] "
        f"({dex_regime})"
    )
    console.print(f"  {'CPR Raw':<22} {cpr_raw:.3f}")
    console.print(f"  {'CPR Notional':<22} {cpr_notional:.3f}")
###########################################################################

    # --- HVL and Vol Trigger (ticker price space) ---
    hvl = compute_hvl(call_gex, put_gex)
    max_pain = compute_max_pain(calls, puts)
    vol_trigger = compute_vol_trigger(
        call_gex, gamma_flip=0.0
    )  # placeholder; recomputed below

    # --- Skew-corrected gamma flip ---
    # This line can be changes to easily swap between a hardcoded alpha_skew and one calculated based on the options chain
    skew_slope, skew_r2 = compute_skew_slope(calls, puts, spot)
    skew_alpha = 0.3 + 0.6 * skew_r2  # scales 0.3 (noisy fit) to 0.9 (clean fit)
    # skew_alpha = 0.7

######################################################################################
    console.print()
    console.print(Rule("[bold blue]Volatility[/bold blue]"))
    console.print()
    console.print(f"  {'ATM Skew Slope':<22} {skew_slope:.5f}")
    console.print(f"  {'R²':<22} {skew_r2:.3f}")
    console.print(f"  {'Alpha':<22} {skew_alpha:.2f}")
########################################################################################
    #print(f"  Computing gamma flip...")




    gamma_flip = find_gamma_flip(
        calls, puts, spot, skew_slope, skew_alpha, risk_free_rate
    )

    vol_trigger = compute_vol_trigger(call_gex, gamma_flip)

    # Save ticker-space walls for next run's hysteresis comparison
    etf_call_wall = float(call_wall)
    etf_put_wall = float(put_wall)
    etf_gamma_flip = float(gamma_flip)


##### Descending Sorted Gex Levels #######################################################################

    from rich.panel import Panel
    from rich import box

    console.print()
    console.print(Rule("[bold yellow]GEX Levels[/bold yellow]"))
    console.print()

    levels = [
        ("Gamma Flip", gamma_flip),
        ("Call Wall", call_wall),
        ("Put Wall", put_wall),
        ("HVL", hvl),
        ("Vol Trigger", vol_trigger),
        ("Max Pain", max_pain),
    ]

    # Sort descending by price
    levels.sort(key=lambda x: x[1], reverse=True)

    # Build the text lines inside the block
    lines = []
    for label, val in levels:
        lines.append(f"  {label:<22} ${val:,.2f}")

    content = "\n".join(lines)

    # Wrap it in a panel with a down arrow on the right side of the border
    console.print(Panel(content, box=box.ROUNDED, expand=False, title="[cyan]⬇[/cyan]", title_align="right"))

    console.print()

#############################################################################


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
                max_pain *= ratio
                net_dex *= ratio
                spot = index_price
            except Exception as e:
                console.print(
                    f"[bold italic grey42]Warning: could not fetch {index_ticker}, levels stay in {symbol} price space: {e}[/bold italic grey42]"
                )


        else:
            console.print(
                f"[bold italic grey42]No index conversion requested — levels stay in {symbol} price space[/bold italic grey42]"
            )





    # Convert profile strikes to output price space
    gex_profile = sorted(
        [(round(s * ratio), int(profile_by_strike[s])) for s in profile_by_strike],
        key=lambda p: p[0],
    )
    # print(
    #     f"  GEX profile: {len(gex_profile)} strikes ({sum(1 for _, g in gex_profile if g > 0)} call, {sum(1 for _, g in gex_profile if g < 0)} put)"
    # )

    console.print(
        f"  GEX profile: [cyan]{len(gex_profile)}[/cyan] strikes "
        f"({sum(1 for _, g in gex_profile if g > 0)} call, "
        f"{sum(1 for _, g in gex_profile if g < 0)} put)"
    )

    console.print()
    console.print()
    console.print(
        Rule(characters="═", style="bold dark_magenta")
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
        "vol_close": float(vol_close),
        "vol_ticker": vol_ticker or "",
        "gex_profile": gex_profile,
    }

