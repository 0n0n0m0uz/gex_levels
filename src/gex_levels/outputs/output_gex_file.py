import json
import os


from gex_levels.config import OUTPUT_DIR
from rich.console import Console


console = Console(force_terminal=True)

def write_gex_file(data, tenor):
    """Write one DTE window's data to its own file — gex_{symbol}_{tenor}.json.
    One file per tenor so a run of one window never touches another
    window's file (each is only ever written by its own run).
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    sym = data["symbol"]
    path = os.path.join(OUTPUT_DIR, f"gex_{sym}_{tenor}.json")

    output_data = {
        "symbol": sym,
        "underlying": round(data["underlying"], 2),
        "timestamp": data["timestamp"],
        "tenor": str(tenor),
        "gex_regime": data["gex_regime"],
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
        "pcr_raw": round(data["pcr_raw"], 4),
        "pcr_notional": round(data["pcr_notional"], 4),
        "etf_gamma_flip": round(data["etf_gamma_flip"], 2),
        "etf_call_wall": round(data["etf_call_wall"], 2),
        "etf_put_wall": round(data["etf_put_wall"], 2),
        #"gex_profile": data.get("gex_profile", [])
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=4)

    console.print(
        f"[bold italic grey42]Exported data to '{path}' [/bold italic grey42]"
    )
