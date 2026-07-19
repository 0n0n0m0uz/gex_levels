import os
import sys

import numpy as np
from scipy.stats import norm


from gex_levels.config import SKEW_ALPHA, RISK_FREE_RATE, OUTPUT_DIR, WALL_HYSTERESIS
from gex_levels.black_scholes.black_scholes_calcs import bs_gamma, bs_delta


def compute_per_strike_gex(arr, spot, r, sign=1.0):
    """Aggregate dollar gamma per 1% move by strike.
    This is interpreted as the $ amount of the underlying that market makers would need to buy/sell to remain hedged (delta-neutral)
    Uses: sign * gamma * OI * 100 * S^2 * 0.01
    This is the standard institutional scaling for dollar gamma exposure.
    Calls get sign=+1 (dealers long gamma), puts get sign=-1 (dealers short gamma).
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
    """Compute net dealer delta exposure (DEX).

    Dealers are short calls (negative delta) and long puts (positive delta
    from their hedge), so net DEX = -call_delta_notional + put_delta_notional.
    A negative NET_DEX means dealers are net short delta (must buy to hedge
    as price rises) — amplifies upside moves.
    Returns (net_dex, regime_str).
    """
    net = 0.0
    for arr, is_call, sign in [(calls, True, -1.0), (puts, False, +1.0)]:
        if len(arr) == 0:
            continue
        K, OI, T, IV = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
        delta = bs_delta(spot, K, T, r, IV, is_call=is_call)
        net += sign * float(np.sum(delta * OI * 100))
    regime = "dealer_long" if net >= 0 else "dealer_short"
    return net, regime


def compute_cpr(calls, puts):
    """Compute call/put ratios.

    CPR_RAW      = total call OI / total put OI
    CPR_NOTIONAL = sum(call OI * strike) / sum(put OI * strike)
    Both > 1 means more call activity (bullish skew).
    """
    if len(calls) == 0 or len(puts) == 0:
        return 1.0, 1.0
    call_oi = float(np.sum(calls[:, 1]))
    put_oi = float(np.sum(puts[:, 1]))
    call_notl = float(np.sum(calls[:, 1] * calls[:, 0]))
    put_notl = float(np.sum(puts[:, 1] * puts[:, 0]))
    cpr_raw = call_oi / put_oi if put_oi > 0 else 1.0
    cpr_notl = call_notl / put_notl if put_notl > 0 else 1.0
    return cpr_raw, cpr_notl


def compute_hvl(call_gex, put_gex):
    """Compute High Volatility Level — notional-weighted center of mass
    of the absolute GEX profile.

    This is the price at which dealer hedging pressure is most balanced
    across strikes. Above it dealers are net long gamma (dampening);
    below it net short gamma (amplifying).
    """
    combined = {}
    for d in (call_gex, put_gex):
        for strike, gex in d.items():
            combined[strike] = combined.get(strike, 0.0) + abs(gex)
    total_weight = sum(combined.values())
    if total_weight == 0:
        return 0.0
    return sum(strike * weight for strike, weight in combined.items()) / total_weight


def compute_wall_zones(gex_dict, spot, direction="call"):
    """Compute gamma wall and zone edges using 25%-75% cumulative GEX concentration.

    Same methodology as the 0DTE script — more meaningful than single-strike max
    because real gamma walls are zones of dealer hedging pressure, not a point.

    direction="call": sweeps upward from spot through positive-GEX strikes
    direction="put":  sweeps downward from spot through negative-GEX strikes

    Returns (wall, wall_low, wall_high):
      wall       = 75% cumulative threshold strike (the primary level)
      wall_low   = 25% threshold (inner edge of the zone)
      wall_high  = 75% threshold (outer edge; same as wall for calls, or
                   the deeper put strike for puts)
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


# def compute_vol_trigger(call_gex, gamma_flip):
#     """Compute Vol Trigger — lowest call-side strike with meaningful
#     positive GEX at or above the gamma flip.
#
#     This marks the level where call dealer hedging (buy pressure) kicks in
#     meaningfully on the upside.  Often sits between Gamma Flip and Call Wall.
#     """
#     threshold = max(call_gex.values()) * 0.05 if call_gex else 0.0
#     candidates = sorted(
#         [s for s, g in call_gex.items() if g >= threshold and s >= gamma_flip]
#     )
#     return float(candidates[0]) if candidates else float(gamma_flip)


def compute_vol_trigger(call_gex: dict[float, float], gamma_flip: float) -> float:
    """Compute Vol Trigger — lowest call-side strike with meaningful
    positive GEX at or above the gamma flip.

    This marks the level where call dealer hedging (buy pressure) kicks in
    meaningfully on the upside.  Often sits between Gamma Flip and Call Wall.
    """
    if not call_gex:
        return float(gamma_flip)

    threshold = max(call_gex.values()) * 0.05

    # 1. Cast explicitly to float during extraction to guarantee types
    # 2. Type-hint 'candidates' so the IDE and future-you know exactly what it holds
    candidates: list[float] = sorted(
        [
            float(s)
            for s, g in call_gex.items()
            if g >= threshold and float(s) >= gamma_flip
        ]
    )

    return candidates[0] if candidates else float(gamma_flip)


def compute_skew_slope(calls, puts, spot):
    """Compute empirical ATM skew slope (dIV/dStrike) from near-ATM puts.

    Returns a negative number for typical equity index skew.
    Used as a linear approximation — real skew is nonlinear, so treat
    the resulting gamma flip as a smoothed proxy, not a precise level.
    """
    if len(puts) == 0:
        return 0.0

    K = puts[:, 0]
    IV = puts[:, 3]
    near_atm = (K > spot * 0.95) & (K < spot * 1.05)
    K_near = K[near_atm]
    IV_near = IV[near_atm]

    if len(K_near) < 3:
        return 0.0
    # This manual slope calculation was changed to use a built-in method that also returns R2
    # slope, _ = np.polyfit(K_near, IV_near, 1)
    from scipy.stats import linregress

    result = linregress(K_near, IV_near)
    return float(result.slope), float(result.rvalue**2)


def find_gamma_flip(
    calls, puts, spot, skew_slope, skew_alpha=SKEW_ALPHA, r=RISK_FREE_RATE
):
    """Find gamma flip with skew-corrected IV.

    Sweeps hypothetical spot levels and computes net GEX at each using
    S^2 * 0.01 scaling. The zero crossing nearest current spot is the flip.
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


def read_previous_etf_walls(symbol, out_symbol):
    """Read previous ETF-space walls from existing file for hysteresis.

    These are the raw ETF strikes before index conversion, stored as
    ETF_CALL_WALL / ETF_PUT_WALL in the output file.
    """
    path = os.path.join(OUTPUT_DIR, f"gex_{out_symbol}.txt")
    prev = {"ETF_CALL_WALL": 0.0, "ETF_PUT_WALL": 0.0}
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                if key in prev:
                    prev[key] = float(val)
    except (FileNotFoundError, ValueError):
        pass
    return prev["ETF_CALL_WALL"], prev["ETF_PUT_WALL"]


def apply_hysteresis(gex_map, new_wall, prev_wall):
    """Only move the wall if new candidate is >10% stronger than previous.

    Both new_wall and prev_wall must be in the same price space as gex_map
    (ETF strikes). Comparison uses absolute GEX magnitude.
    """
    if prev_wall == 0.0 or prev_wall not in gex_map:
        return new_wall

    new_strength = abs(gex_map[new_wall])
    prev_strength = abs(gex_map.get(prev_wall, 0.0))

    if prev_strength == 0:
        return new_wall

    if new_strength > prev_strength * (1.0 + WALL_HYSTERESIS):
        return new_wall
    else:
        return prev_wall


def _derive_profile_levels(data):
    """Extract key levels, net GEX string, and top 5 nodes from a data dict.

    Wall zones (cw_low/cw_high, pw_low/pw_high) now come directly from
    compute_gex_levels via compute_wall_zones — no longer derived post-hoc.
    """
    cw = data["call_wall"]
    pw = data["put_wall"]
    profile = data.get("gex_profile", [])

    # Wall zones pre-computed in compute_gex_levels
    cw_low = data.get("call_wall_low", cw)
    cw_high = data.get("call_wall_high", cw)
    pw_low = data.get("put_wall_low", pw)
    pw_high = data.get("put_wall_high", pw)

    # Key levels: 2nd and 3rd strongest call/put gamma strikes
    call_nodes = sorted(
        [(p, g) for p, g in profile if g > 0], key=lambda x: x[1], reverse=True
    )
    put_nodes = sorted(
        [(p, g) for p, g in profile if g < 0], key=lambda x: abs(x[1]), reverse=True
    )

    def next_levels(nodes, wall, n=2):
        others = [p for p, _ in nodes if round(p) != round(wall)]
        return others[:n] + [0.0] * max(0, n - len(others))

    kc2, kc3 = next_levels(call_nodes, cw)
    kp2, kp3 = next_levels(put_nodes, pw)

    net_gex = data["net_gex"]
    abs_gex = abs(net_gex)
    sign_str = "+" if net_gex >= 0 else "-"
    if abs_gex >= 1e9:
        net_gex_str = f'"{sign_str}{abs_gex / 1e9:.2f}B"'
    elif abs_gex >= 1e6:
        net_gex_str = f'"{sign_str}{abs_gex / 1e6:.1f}M"'
    else:
        net_gex_str = f'"{sign_str}{abs_gex / 1e3:.0f}K"'

    top5 = sorted(profile, key=lambda x: abs(x[1]), reverse=True)[:5]
    while len(top5) < 5:
        top5.append((0.0, 0))

    return dict(
        kc2=kc2,
        kc3=kc3,
        kp2=kp2,
        kp3=kp3,
        cw_low=cw_low,
        cw_high=cw_high,
        pw_low=pw_low,
        pw_high=pw_high,
        net_gex_str=net_gex_str,
        top5=top5,
    )