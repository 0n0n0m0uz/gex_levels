import os
import sys


def derive_profile_levels(data):
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


def print_pinescript_block(data30=None, data90=None):
    """Print a ready-to-paste Pine Script update block with whichever DTE window(s) are given."""
    header = data90 or data30
    sym = header["symbol"]
    ts = header["timestamp"][:10]
    underlying = header["underlying"]

    sep = "=" * 63
    print()
    print(f"-- PASTE INTO PINE SCRIPT ({sym}) --")
    print(f"// {sep}")
    print(f"//  PASTE UPDATED DATA HERE EACH DAY")
    print(f"// {sep}")
    print(f'var string SYM        = "{sym}"')
    print(f'var string TIMESTAMP  = "{ts}"')
    print(f"var float UNDERLYING  = {underlying:.2f}")
    print()
    if data30:
        _print_dte_section(data30, "_30", derive_profile_levels(data30))
    if data90:
        _print_dte_section(data90, "_90", derive_profile_levels(data90))
    print(f"// {sep}")
    print()

def _print_dte_section(data, suffix, levels):
    """Print one DTE section (30 or 90) of the Pine Script paste block."""
    s = suffix  # "_30" or "_90"
    cw = data["call_wall"]
    pw = data["put_wall"]
    gf = data["gamma_flip"]
    vt = data["vol_trigger"]
    hvl = data["hvl"]
    mp = data["max_pain"]
    nd = data["net_dex"]
    dr = data["dex_regime"]
    cr = data["pcr_raw"]
    cn = data["pcr_notional"]
    re = data["gex_regime"]
    l = levels

    print(
        f"// -- {suffix.strip('_')}D levels ----------------------------------------------"
    )
    print(f'var string REGIME{s}     = "{re}"')
    print(f"var float GAMMA_FLIP{s}  = {gf:.2f}")
    print(f"var float VOL_TRIGGER{s} = {vt:.2f}")
    print(f"var float HVL{s}         = {hvl:.2f}")
    print(f"var float MAX_PAIN{s}    = {mp:.2f}")
    print(f"var float CALL_WALL{s}   = {cw:.2f}")
    print(f"var float CW_LOW{s}      = {l['cw_low']:.2f}")
    print(f"var float CW_HIGH{s}     = {l['cw_high']:.2f}")
    print(f"var float PUT_WALL{s}    = {pw:.2f}")
    print(f"var float PW_LOW{s}      = {l['pw_low']:.2f}")
    print(f"var float PW_HIGH{s}     = {l['pw_high']:.2f}")
    print(f"var float KEY_CALL_2{s}  = {l['kc2']:.2f}")
    print(f"var float KEY_CALL_3{s}  = {l['kc3']:.2f}")
    print(f"var float KEY_PUT_2{s}   = {l['kp2']:.2f}")
    print(f"var float KEY_PUT_3{s}   = {l['kp3']:.2f}")
    print(f"var string NET_GEX{s}    = {l['net_gex_str']}")
    print(f"var float  NET_DEX{s}    = {nd:.1f}")
    print(f'var string DEX_REGIME{s} = "{dr}"')
    print(f"var float  PCR_RAW{s}    = {cr:.4f}")
    print(f"var float  PCR_NOTL{s}   = {cn:.4f}")
    for i, (price, gex) in enumerate(l["top5"], 1):
        print(f"var float GEX_NODE{i}_P{s} = {price:.2f}")
        print(f"var float GEX_NODE{i}_V{s} = {gex:.1f}")
    print()