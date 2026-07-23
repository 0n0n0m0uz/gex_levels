import os
import sys


from gex_levels.gex.gex_calculations import derive_profile_levels


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
    cr = data["cpr_raw"]
    cn = data["cpr_notl"]
    re = data["regime"]
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
    print(f"var float  CPR_RAW{s}    = {cr:.4f}")
    print(f"var float  CPR_NOTL{s}   = {cn:.4f}")
    for i, (price, gex) in enumerate(l["top5"], 1):
        print(f"var float GEX_NODE{i}_P{s} = {price:.2f}")
        print(f"var float GEX_NODE{i}_V{s} = {gex:.1f}")
    print()