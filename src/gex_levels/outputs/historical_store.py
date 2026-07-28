import pandas as pd

from gex_levels.config import HISTORY_DIR


def save_chain_snapshot(symbol, date_str, raw_chain):
    """Persist one day's raw per-contract chain (strike/OI/volume/IV) for
    `symbol`, captured before collect_chain() DTE-weights the OI, drops
    volume, and applies the +-20% OTM filter for GEX math. One Parquet file
    per symbol per day (data/history/{symbol}/chain/{date}.parquet) — a
    rerun on the same day just overwrites that single file, no merge needed.

    Schwab and yfinance name the volume column differently
    (totalVolume vs volume) — normalized to "volume" here.
    """
    rows = []
    for exp_str, calls_df, puts_df in raw_chain:
        for df, option_type in ((calls_df, "call"), (puts_df, "put")):
            volume_col = "totalVolume" if "totalVolume" in df.columns else "volume"
            for _, row in df.iterrows():
                rows.append({
                    "expiration": exp_str,
                    "option_type": option_type,
                    "strike": float(row["strike"]),
                    "open_interest": int(row.get("openInterest", 0) or 0),
                    "volume": int(row.get(volume_col, 0) or 0),
                    "implied_vol": float(row.get("impliedVolatility", 0) or 0),
                })

    snapshot = pd.DataFrame(rows)
    out_dir = HISTORY_DIR / symbol / "chain"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}.parquet"
    snapshot.to_parquet(out_path, index=False)
    return out_path, snapshot


def save_daily_summary(symbol, date_str, tenor, data):
    """Append/replace one day's summary row (keyed by date+tenor) for
    `symbol`. Small — read the existing per-symbol file, drop any row for
    this exact date+tenor, append the new one, rewrite.
    """
    row = {
        "date": date_str,
        "tenor": tenor,
        "underlying": data["underlying"],
        "gex_regime": data["gex_regime"],
        "gamma_flip": data["gamma_flip"],
        "vol_trigger": data["vol_trigger"],
        "hvl": data["hvl"],
        "max_pain": data["max_pain"],
        "call_wall": data["call_wall"],
        "call_wall_low": data["call_wall_low"],
        "call_wall_high": data["call_wall_high"],
        "put_wall": data["put_wall"],
        "put_wall_low": data["put_wall_low"],
        "put_wall_high": data["put_wall_high"],
        "net_gex": data["net_gex"],
        "net_dex": data["net_dex"],
        "dex_regime": data["dex_regime"],
        "cpr_raw": data["cpr_raw"],
        "cpr_notional": data["cpr_notional"],
    }

    out_dir = HISTORY_DIR / symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "summary.parquet"

    if path.exists():
        existing = pd.read_parquet(path)
        existing = existing[
            ~((existing["date"] == date_str) & (existing["tenor"] == tenor))
        ]
        combined = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
    else:
        combined = pd.DataFrame([row])

    combined.to_parquet(path, index=False)
    return path
