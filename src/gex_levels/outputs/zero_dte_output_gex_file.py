import json
import os

from gex_levels.config import OUTPUT_DIR
from rich.console import Console

console = Console(force_terminal=True)


def write_gex_file_0dte(data):
    """0DTE analogue of output_gex_file.write_gex_file() — same JSON shape,
    minus the etf_gamma_flip/etf_call_wall/etf_put_wall hysteresis-baseline
    fields (0DTE has no hysteresis, so there's no previous-run value for a
    future run to compare against).
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    sym = data["symbol"]
    path = os.path.join(OUTPUT_DIR, f"gex_{sym}_0dte.json")

    output_data = {
        "symbol": sym,
        "underlying": round(data["underlying"], 2),
        "timestamp": data["timestamp"],
        "tenor": "0dte",
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
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=4)

    console.print(
        f"[bold italic grey42]Exported data to '{path}' [/bold italic grey42]"
    )
