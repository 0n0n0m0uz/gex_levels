import numpy as np
from datetime import datetime
from scipy.stats import norm
from scipy.stats import linregress

from gex_levels.config import SKEW_ALPHA, RISK_FREE_RATE
from gex_levels.black_scholes.black_scholes_calcs import bs_gamma, bs_delta

# 0DTE analogue of gex.gex_calculations — same math, minus the two
# hysteresis-related functions (apply_hysteresis, read_previous_etf_walls):
# 0DTE walls must be reactive, not sticky, so there is no previous-run
# baseline to compare against.


def collect_chain_0dte(raw_chain, spot, open_ratio=0.35):
    """0DTE analogue of getData.fetch_spot.collect_chain(): narrows raw_chain
    down to just today's expiration and builds [strike, effective_OI, T, IV]
    arrays (same 4-column shape the rest of this module expects).

    effective_OI = openInterest + int(volume * open_ratio) — additive, not
    substitutive. OI is the known baseline (yesterday's open positions);
    volume * open_ratio estimates new positions opened today. Accumulated
    rather than substituted because OI and volume measure different things:
    OI is net open, volume is gross transactions including closings.
    open_ratio=0.35 is a conservative estimate of the opening fraction of
    today's 0DTE volume (the rest is closings/rolls). Unlike the daily
    collect_chain(), openInterest==0 is allowed through as long as volume
    is present — that's the whole point of folding volume in for strikes
    that only opened today.

    Column name for volume differs by source: Schwab's parser emits
    "totalVolume", yfinance's option_chain() emits "volume" — both handled.

    Returns (calls, puts, num_expirations) — num_expirations is 0 or 1.
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    seconds_left = max((market_close - now).total_seconds(), 60)
    T = seconds_left / (252 * 6.5 * 3600)  # annualized trading time left today

    calls_list, puts_list = [], []
    num_expirations = 0

    for exp_str, calls_df, puts_df in raw_chain:
        if exp_str != today_str:
            continue
        num_expirations += 1

        for df, out_list in [(calls_df, calls_list), (puts_df, puts_list)]:
            vol_col = "totalVolume" if "totalVolume" in df.columns else "volume"
            df = df.fillna(0)
            mask = (
                (df["impliedVolatility"] > 0.001)
                & (df["strike"] > 0)
                & (df["strike"] > spot * 0.85)
                & (df["strike"] < spot * 1.15)
            )
            for _, row in df[mask].iterrows():
                effective_oi = row["openInterest"] + int(row[vol_col] * open_ratio)
                if effective_oi <= 0:
                    continue
                out_list.append(
                    [row["strike"], effective_oi, T, row["impliedVolatility"]]
                )

    calls = np.array(calls_list) if calls_list else np.empty((0, 4))
    puts = np.array(puts_list) if puts_list else np.empty((0, 4))
    return calls, puts, num_expirations


def compute_per_strike_gex(arr, spot, r, sign=1.0):
    """Aggregate dollar gamma per 1% move by strike — identical to the daily
    version; effective_OI is already baked into the OI column by
    collect_chain_0dte() above.
    """
    if len(arr) == 0:
        return {}
    K, OI, T, IV = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    gamma = bs_gamma(spot, K, T, r, IV)
    gex = sign * gamma * OI * 100 * spot * spot * 0.01
    result = {}
    for i in range(len(K)):
        result[K[i]] = result.get(K[i], 0.0) + gex[i]
    return result


def compute_net_dex(calls, puts, spot, r):
    """Compute net dealer delta exposure (DEX). Identical to the daily version."""
    net = 0.0
    for arr, is_call, sign in [(calls, True, -1.0), (puts, False, +1.0)]:
        if len(arr) == 0:
            continue
        K, OI, T, IV = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
        delta = bs_delta(spot, K, T, r, IV, is_call=is_call)
        net += sign * float(np.sum(delta * OI * 100))
    regime = "dealer_long" if net >= 0 else "dealer_short"
    return net, regime


def compute_pcr(calls, puts):
    """Compute put/call ratios (standard PCR convention — puts over calls).
    Identical to the daily version.
    """
    if len(calls) == 0 or len(puts) == 0:
        return 1.0, 1.0
    call_oi = float(np.sum(calls[:, 1]))
    put_oi = float(np.sum(puts[:, 1]))
    call_notl = float(np.sum(calls[:, 1] * calls[:, 0]))
    put_notl = float(np.sum(puts[:, 1] * puts[:, 0]))
    pcr_raw = put_oi / call_oi if call_oi > 0 else 1.0
    pcr_notional = put_notl / call_notl if call_notl > 0 else 1.0
    return pcr_raw, pcr_notional


def compute_max_pain(calls, puts):
    """Compute max pain. Identical to the daily version."""
    if len(calls) == 0 and len(puts) == 0:
        return 0.0

    call_K = calls[:, 0] if len(calls) else np.empty(0)
    call_OI = calls[:, 1] if len(calls) else np.empty(0)
    put_K = puts[:, 0] if len(puts) else np.empty(0)
    put_OI = puts[:, 1] if len(puts) else np.empty(0)

    candidates = np.unique(np.concatenate([call_K, put_K]))
    S = candidates[:, np.newaxis]

    call_pain = np.sum(np.maximum(S - call_K[np.newaxis, :], 0) * call_OI[np.newaxis, :], axis=1)
    put_pain = np.sum(np.maximum(put_K[np.newaxis, :] - S, 0) * put_OI[np.newaxis, :], axis=1)

    return float(candidates[np.argmin(call_pain + put_pain)])


def compute_hvl(call_gex, put_gex):
    """Compute High Volatility Level. Identical to the daily version."""
    combined = {}
    for d in (call_gex, put_gex):
        for strike, gex in d.items():
            combined[strike] = combined.get(strike, 0.0) + abs(gex)
    total_weight = sum(combined.values())
    if total_weight == 0:
        return 0.0
    return sum(strike * weight for strike, weight in combined.items()) / total_weight


def compute_wall_zones(gex_dict, spot, direction="call"):
    """Compute gamma wall and zone edges using 25%-75% cumulative GEX
    concentration. Identical to the daily version — no hysteresis is layered
    on top for 0DTE, so the raw zone this returns is used as-is.
    """
    if not gex_dict:
        return spot, spot, spot

    if direction == "call":
        strikes = sorted([s for s in gex_dict if s >= spot and gex_dict[s] > 0])
        total = sum(gex_dict[s] for s in strikes)
    else:
        strikes = sorted(
            [s for s in gex_dict if s <= spot and gex_dict[s] < 0], reverse=True
        )
        total = sum(abs(gex_dict[s]) for s in strikes)

    if not strikes or total <= 0:
        fallback = (
            max(gex_dict, key=gex_dict.get)
            if direction == "call"
            else max(gex_dict, key=lambda k: abs(gex_dict[k]))
        )
        return fallback, fallback, fallback

    cum = 0.0
    wall = wall_low = wall_high = strikes[0]
    found_lo = found_hi = False

    for s in strikes:
        cum += gex_dict[s] if direction == "call" else abs(gex_dict[s])
        if not found_lo and cum >= total * 0.25:
            wall_low = s
            found_lo = True
        if not found_hi and cum >= total * 0.75:
            wall_high = s
            wall = s
            found_hi = True
            break

    if not found_hi:
        wall_high = wall = strikes[-1]
    if not found_lo:
        wall_low = strikes[0]

    return wall, wall_low, wall_high


def compute_vol_trigger(call_gex: dict[float, float], gamma_flip: float) -> float:
    """Compute Vol Trigger. Identical to the daily version."""
    if not call_gex:
        return float(gamma_flip)

    threshold = max(call_gex.values()) * 0.05

    candidates: list[float] = sorted(
        [
            float(s)
            for s, g in call_gex.items()
            if g >= threshold and float(s) >= gamma_flip
        ]
    )

    return candidates[0] if candidates else float(gamma_flip)


def compute_skew_slope(calls, puts, spot):
    """Compute empirical ATM skew slope (dIV/dStrike). Identical to the
    daily version.
    """
    if len(puts) == 0:
        return 0.0, 0.0

    K = puts[:, 0]
    IV = puts[:, 3]
    near_atm = (K > spot * 0.95) & (K < spot * 1.05)
    K_near = K[near_atm]
    IV_near = IV[near_atm]

    if len(K_near) < 3:
        return 0.0, 0.0

    result = linregress(K_near, IV_near)
    return float(result.slope), float(result.rvalue**2)


def find_gamma_flip(
    calls, puts, spot, skew_slope, skew_alpha=SKEW_ALPHA, r=RISK_FREE_RATE
):
    """Find gamma flip with skew-corrected IV. Identical to the daily
    version — the ±15% sweep range collect_chain_0dte() filters strikes to
    already matches the ±15% hyp range used here.
    """
    if len(calls) == 0 and len(puts) == 0:
        return spot

    hyp = np.linspace(spot * 0.85, spot * 1.15, 300)
    net_gex = np.zeros(len(hyp))

    spot_shift = spot - hyp

    for arr, sign in [(calls, 1.0), (puts, -1.0)]:
        if len(arr) == 0:
            continue
        K = arr[:, 0]
        OI = arr[:, 1]
        T = arr[:, 2]
        IV = arr[:, 3]

        S = hyp[:, np.newaxis]
        IV_base = IV[np.newaxis, :]
        T_b = T[np.newaxis, :]
        OI_b = OI[np.newaxis, :]

        IV_adj = IV_base + skew_alpha * skew_slope * spot_shift[:, np.newaxis]
        IV_adj = np.clip(IV_adj, 0.01, 5.0)

        with np.errstate(divide="ignore", invalid="ignore"):
            sqrt_T = np.sqrt(T_b)
            d1 = (np.log(S / K[np.newaxis, :]) + (r + IV_adj**2 / 2) * T_b) / (
                IV_adj * sqrt_T
            )
            gamma = norm.pdf(d1) / (S * IV_adj * sqrt_T)
            gamma = np.nan_to_num(gamma, nan=0.0, posinf=0.0, neginf=0.0)

        gex = gamma * OI_b * 100 * S * S * 0.01
        net_gex += sign * np.sum(gex, axis=1)

    sign_changes = np.where(np.diff(np.sign(net_gex)))[0]
    if len(sign_changes) > 0:
        midpoints = (hyp[sign_changes] + hyp[sign_changes + 1]) / 2
        closest = sign_changes[np.argmin(np.abs(midpoints - spot))]
        i = closest
        denom = abs(net_gex[i]) + abs(net_gex[i + 1])
        if denom > 0:
            frac = abs(net_gex[i]) / denom
            return float(hyp[i] + frac * (hyp[i + 1] - hyp[i]))

    return float(spot)


def convert_to_index_space(ratio, gamma_flip, call_wall, put_wall, hvl, vol_trigger, max_pain, net_dex):
    """Scale ticker-space levels into index/futures price space. Identical
    to the daily version.
    """
    return (
        gamma_flip * ratio,
        call_wall * ratio,
        put_wall * ratio,
        hvl * ratio,
        vol_trigger * ratio,
        max_pain * ratio,
        net_dex * ratio,
    )
