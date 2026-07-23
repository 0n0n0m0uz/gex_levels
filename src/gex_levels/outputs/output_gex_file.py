import json
import os
import sys

from gex_levels.config import OUTPUT_DIR
from rich.console import Console
from rich.rule import Rule

console = Console(force_terminal=True)

def write_gex_file(data30=None, data90=None):
    """Write whichever DTE window(s) are given to a single key=value text file."""
    header = data90 or data30
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    sym = header["symbol"]
    path = os.path.join(OUTPUT_DIR, f"gex_{sym}.json")

    def write_section(output, data, suffix):
        s = suffix
        output.write(f"REGIME{s}={data['regime']}\n")
        output.write(f"GAMMA_FLIP{s}={data['gamma_flip']:.2f}\n")
        output.write(f"VOL_TRIGGER{s}={data['vol_trigger']:.2f}\n")
        output.write(f"HVL{s}={data['hvl']:.2f}\n")
        output.write(f"CALL_WALL{s}={data['call_wall']:.2f}\n")
        output.write(
            f"CALL_WALL_LOW{s}={data.get('call_wall_low', data['call_wall']):.2f}\n"
        )
        output.write(
            f"CALL_WALL_HIGH{s}={data.get('call_wall_high', data['call_wall']):.2f}\n"
        )
        output.write(f"PUT_WALL{s}={data['put_wall']:.2f}\n")
        output.write(f"PUT_WALL_LOW{s}={data.get('put_wall_low', data['put_wall']):.2f}\n")
        output.write(f"PUT_WALL_HIGH{s}={data.get('put_wall_high', data['put_wall']):.2f}\n")
        output.write(f"NET_GEX{s}={data['net_gex']:.0f}\n")
        output.write(f"NET_DEX{s}={data['net_dex']:.0f}\n")
        output.write(f"DEX_REGIME{s}={data['dex_regime']}\n")
        output.write(f"CPR_RAW{s}={data['cpr_raw']:.4f}\n")
        output.write(f"CPR_NOTIONAL{s}={data['cpr_notl']:.4f}\n")
        output.write(f"ETF_GAMMA_FLIP{s}={data['etf_gamma_flip']:.2f}\n")
        output.write(f"ETF_CALL_WALL{s}={data['etf_call_wall']:.2f}\n")
        output.write(f"ETF_PUT_WALL{s}={data['etf_put_wall']:.2f}\n")
        # profile = data.get("gex_profile", [])
        # if profile:
        #     pairs = ",".join(f"{strike}:{gex}" for strike, gex in profile)
        #     output.write(f"GEX_PROFILE{s}={pairs}\n")

    def build_section(data):
        return {
            "regime": data["regime"],
            "gamma_flip": round(data["gamma_flip"], 2),
            "vol_trigger": round(data["vol_trigger"], 2),
            "hvl": round(data["hvl"], 2),
            "max_pain": round(data["max_pain"], 2),
            "call_wall": round(data["call_wall"], 2),
            "call_wall_low": round(data.get("call_wall_low", data["call_wall"]), 2),
            "call_wall_high": round(data.get("call_wall_high", data["call_wall"]), 2),
            "put_wall": round(data["put_wall"], 2),
            "put_wall_low": round(data.get("put_wall_low", data["put_wall"]), 2),
            "put_wall_high": round(data.get("put_wall_high", data["put_wall"]), 2),
            "net_gex": int(round(data["net_gex"])),
            "net_dex": int(round(data["net_dex"])),
            "dex_regime": data["dex_regime"],
            "cpr_raw": round(data["cpr_raw"], 4),
            "cpr_notional": round(data["cpr_notl"], 4),
            "etf_gamma_flip": round(data["etf_gamma_flip"], 2),
            "etf_call_wall": round(data["etf_call_wall"], 2),
            "etf_put_wall": round(data["etf_put_wall"], 2),
            #"gex_profile": data.get("gex_profile", [])
        }

    output_data = {
        "symbol": sym,
        "underlying": round(header["underlying"], 2),
        "timestamp": header["timestamp"]
    }

    if header.get("vol_close", 0) > 0:
        vol_key = "VXN_CLOSE" if "VXN" in header.get("vol_ticker", "").upper() else "VIX_CLOSE"
        output_data[vol_key] = round(header["vol_close"], 2)

    tenors = {}
    if data30:
        tenors["30"] = build_section(data30)
    if data90:
        tenors["90"] = build_section(data90)

    if tenors:
        output_data["tenors"] = tenors

    # with open(path, "w") as f:
    #     f.write(f"SYMBOL={sym}\n")
    #     f.write(f"UNDERLYING={header['underlying']:.2f}\n")
    #     f.write(f"TIMESTAMP={header['timestamp']}\n")
    #     if header.get("vol_close", 0) > 0:
    #         vol_key = "VXN_CLOSE" if "VXN" in header.get("vol_ticker", "").upper() else "VIX_CLOSE"
    #         f.write(f"{vol_key}={header['vol_close']:.2f}\n")
    #     if data30:
    #         write_section(f, data30, "_30")
    #     if data90:
    #         write_section(f, data90, "_90")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=4)


    console.print(
        f"[bold italic grey42]Exported data to '{path}' [/bold italic grey42]"
    )