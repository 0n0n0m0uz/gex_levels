from gex_levels.outputs.pinescript_output import derive_profile_levels


def print_pinescript_block_0dte(data):
    """0DTE analogue of pinescript_output.print_pinescript_block() — same
    paste-block format and derive_profile_levels() logic (unmodified, reused
    as-is since it's already generic over any single window's dict), just
    for one window instead of the daily _30/_90 pair, so no suffix on the
    variable names.
    """
    sym = data["symbol"]
    ts = data["timestamp"][:10]
    underlying = data["underlying"]
    levels = derive_profile_levels(data)

    gf = data["gamma_flip"]
    vt = data["vol_trigger"]
    hvl = data["hvl"]
    mp = data["max_pain"]
    cw = data["call_wall"]
    pw = data["put_wall"]
    nd = data["net_dex"]
    dr = data["dex_regime"]
    cr = data["pcr_raw"]
    cn = data["pcr_notional"]
    re = data["gex_regime"]

    sep = "=" * 63
    print()
    print(f"-- PASTE INTO PINE SCRIPT ({sym} 0DTE) --")
    print(f"// {sep}")
    print(f"//  PASTE UPDATED DATA HERE EACH DAY  (0DTE)")
    print(f"// {sep}")
    print(f'var string SYM        = "{sym}"')
    print(f'var string TIMESTAMP  = "{ts}"')
    print(f"var float UNDERLYING  = {underlying:.2f}")
    print()
    print(f'var string REGIME     = "{re}"')
    print(f"var float GAMMA_FLIP  = {gf:.2f}")
    print(f"var float VOL_TRIGGER = {vt:.2f}")
    print(f"var float HVL         = {hvl:.2f}")
    print(f"var float MAX_PAIN    = {mp:.2f}")
    print(f"var float CALL_WALL   = {cw:.2f}")
    print(f"var float CW_LOW      = {levels['cw_low']:.2f}")
    print(f"var float CW_HIGH     = {levels['cw_high']:.2f}")
    print(f"var float PUT_WALL    = {pw:.2f}")
    print(f"var float PW_LOW      = {levels['pw_low']:.2f}")
    print(f"var float PW_HIGH     = {levels['pw_high']:.2f}")
    print(f"var float KEY_CALL_2  = {levels['kc2']:.2f}")
    print(f"var float KEY_CALL_3  = {levels['kc3']:.2f}")
    print(f"var float KEY_PUT_2   = {levels['kp2']:.2f}")
    print(f"var float KEY_PUT_3   = {levels['kp3']:.2f}")
    print(f"var string NET_GEX    = {levels['net_gex_str']}")
    print(f"var float  NET_DEX    = {nd:.1f}")
    print(f'var string DEX_REGIME = "{dr}"')
    print(f"var float  PCR_RAW    = {cr:.4f}")
    print(f"var float  PCR_NOTL   = {cn:.4f}")
    for i, (price, gex) in enumerate(levels["top5"], 1):
        print(f"var float GEX_NODE{i}_P = {price:.2f}")
        print(f"var float GEX_NODE{i}_V = {gex:.1f}")
    print(f"// {sep}")
    print()
