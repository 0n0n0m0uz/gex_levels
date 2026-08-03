"""
oi_churn.py - Open Interest vs Volume Churn Report (via Schwab)

Compares today's per-strike open interest against the prior session's
snapshot (for the same DTE window) to estimate how much of today's volume
represents genuinely new open interest vs same-day churn (closes, rolls,
round-trip day trades).

  new_oi_volume = max(OI_today - OI_yesterday, 0), capped at volume
  churn_volume  = volume - new_oi_volume

Requires a prior session's snapshot *for the same window* to compare
against — the first run for a symbol+window combo just establishes the
baseline; run again on a later session to see the actual split.

Usage:
    python reports/oi_churn.py SPY                # --days 30 (default)
    python reports/oi_churn.py SPY --days 90
    python reports/oi_churn.py SPY --0dte
"""

import os
import csv
import json
import argparse
from datetime import datetime


from dotenv import load_dotenv

load_dotenv()

from gex_levels.config import BASE_DIR
from gex_levels.getData.fetch_spot import get_spot, get_chain

DATA_DIR = BASE_DIR / "src" / "gex_levels" / "reports" / "data"

NEAR_DTE = 21  # near-term bucket ceiling

CSV_FIELDS = [
    "exp", "type", "strike", "dte",
    "oi_prior", "oi_today", "delta_oi",
    "volume", "new_oi_vol", "churn_vol",
]


def csv_path(symbol, window_key, ts):
    return os.path.join(DATA_DIR, f"oi_churn_{symbol}_{window_key}_{ts}.csv")


def save_csv(path, rows):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def parse_chain(raw_chain, min_dte, max_dte):
    """Flatten already-resolved chain data (see get_chain()) into
    {"exp|strike|type": {"oi", "volume", "dte"}}.
    """
    today = datetime.now().date()
    snapshot = {}
    for exp_str, calls_df, puts_df in raw_chain:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
        dte = (exp_date - today).days
        if dte < min_dte or dte > max_dte:
            continue
        for df, opt_type in [(calls_df, "call"), (puts_df, "put")]:
            volume_col = "totalVolume" if "totalVolume" in df.columns else "volume"
            for _, row in df.iterrows():
                oi = int(row.get("openInterest", 0) or 0)
                vol = int(row.get(volume_col, 0) or 0)
                key = f"{exp_str}|{row['strike']}|{opt_type}"
                snapshot[key] = {"oi": oi, "volume": vol, "dte": dte}
    return snapshot


HISTORY_DAYS = 10  # sessions of snapshot history to retain per symbol


def state_path(symbol):
    return os.path.join(DATA_DIR, f"oi_churn_{symbol}.json")


def load_history(symbol):
    """{date_str: {window_key: snapshot}} across past sessions. Never mutated by same-day re-runs.

    Dates written by the pre-window version of this script store a flat
    {contract_key: {...}} snapshot directly under the date, not keyed by
    window ("0dte"/"30"/"90") — those old entries are left on disk as-is
    but never match a window lookup (contract keys never collide with a
    window key), so they're effectively invisible to the new logic rather
    than being misread as a same-window baseline.
    """
    try:
        with open(state_path(symbol)) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if set(data.keys()) == {"date", "snapshot"}:  # migrate old single-slot format
        return {data["date"]: data["snapshot"]}
    return data


def latest_prior_session(history, today_str, window_key):
    """Most recent snapshot for `window_key` from a date before today, or None."""
    prior_dates = [
        d
        for d, entry in history.items()
        if d < today_str and isinstance(entry, dict) and window_key in entry
    ]
    if not prior_dates:
        return None
    latest = max(prior_dates)
    return latest, history[latest][window_key]


def save_today(symbol, history, today_str, window_key, snapshot):
    day_entry = history.get(today_str)
    if not isinstance(day_entry, dict):
        day_entry = {}
    day_entry[window_key] = snapshot
    history[today_str] = day_entry
    for stale in sorted(history)[:-HISTORY_DAYS]:
        del history[stale]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(state_path(symbol), "w") as f:
        json.dump(history, f)


INTRADAY_HISTORY_LIMIT = 20  # 0DTE snapshots to retain per day


def latest_prior_intraday(history, today_str, now_ts):
    """Most recent 0DTE snapshot from *earlier today* (same calendar date,
    same-day expiration — a prior calendar day's 0DTE contracts are a
    disjoint set of contracts, never comparable), or None if this is the
    first 0DTE run of the day.
    """
    day_entry = history.get(today_str)
    if not isinstance(day_entry, dict):
        return None
    snapshots = day_entry.get("0dte")
    if not isinstance(snapshots, list):
        return None
    prior_entries = [s for s in snapshots if s["time"] < now_ts]
    if not prior_entries:
        return None
    latest = max(prior_entries, key=lambda s: s["time"])
    return latest["time"], latest["snapshot"]


def save_intraday(symbol, history, today_str, now_ts, snapshot):
    day_entry = history.get(today_str)
    if not isinstance(day_entry, dict):
        day_entry = {}
    snapshots = day_entry.get("0dte")
    if not isinstance(snapshots, list):
        snapshots = []
    snapshots.append({"time": now_ts, "snapshot": snapshot})
    day_entry["0dte"] = snapshots[-INTRADAY_HISTORY_LIMIT:]
    history[today_str] = day_entry
    for stale in sorted(history)[:-HISTORY_DAYS]:
        del history[stale]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(state_path(symbol), "w") as f:
        json.dump(history, f)


def compute_churn(today_snap, prior_snap, incremental_volume=False):
    """Per-contract new-OI vs churn split. Skips contracts with no prior-session baseline.

    incremental_volume: when both snapshots are from the *same trading day*
    (0DTE intraday comparisons), Schwab's totalVolume is a cumulative
    day counter shared by both snapshots, so the volume attributable to
    the window between them is today.volume - prior.volume, not
    today.volume outright. Day-over-day (30/90) comparisons don't need
    this — each trading day's volume counter starts fresh at zero, so
    today's raw volume already excludes any prior day's activity.
    """
    rows = []
    for key, today in today_snap.items():
        prior = prior_snap.get(key)
        if prior is None:
            continue
        exp_str, strike_str, opt_type = key.split("|")
        delta_oi = today["oi"] - prior["oi"]
        volume = (
            max(today["volume"] - prior["volume"], 0)
            if incremental_volume
            else today["volume"]
        )
        new_oi_vol = min(volume, max(delta_oi, 0))
        churn_vol = max(volume - new_oi_vol, 0)
        rows.append(
            {
                "exp": exp_str,
                "strike": float(strike_str),
                "type": opt_type,
                "dte": today["dte"],
                "oi_prior": prior["oi"],
                "oi_today": today["oi"],
                "delta_oi": delta_oi,
                "volume": volume,
                "new_oi_vol": new_oi_vol,
                "churn_vol": churn_vol,
            }
        )
    return rows


def bucket_summary(rows):
    if not rows:
        return {
            "oi_prior": 0,
            "oi_today": 0,
            "volume": 0,
            "new_oi_vol": 0,
            "churn_vol": 0,
            "count": 0,
        }
    return {
        "oi_prior": sum(r["oi_prior"] for r in rows),
        "oi_today": sum(r["oi_today"] for r in rows),
        "volume": sum(r["volume"] for r in rows),
        "new_oi_vol": sum(r["new_oi_vol"] for r in rows),
        "churn_vol": sum(r["churn_vol"] for r in rows),
        "count": len(rows),
    }


TABLE_HEADERS = [
    "Bucket",
    "Contracts",
    "OI Prior",
    "OI Today",
    "Delta OI",
    "Volume",
    "New OI Vol",
    "Churn Vol",
    "Churn %",
]


def bucket_row(label, b):
    churn_pct = (b["churn_vol"] / b["volume"] * 100) if b["volume"] else 0.0
    return [
        label,
        b["count"],
        b["oi_prior"],
        b["oi_today"],
        b["oi_today"] - b["oi_prior"],
        b["volume"],
        b["new_oi_vol"],
        b["churn_vol"],
        f"{churn_pct:.1f}",
    ]


def print_table(rows):
    print("\t".join(TABLE_HEADERS))
    for row in rows:
        print("\t".join(str(v) for v in row))


def main():
    parser = argparse.ArgumentParser(
        description="Compare today's OI vs the prior session (same window) and split volume into new-OI vs churn.",
        epilog="Examples:\n  python oi_churn.py SPY\n  python oi_churn.py SPY --days 90\n  python oi_churn.py SPY --0dte",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "symbol", help="Optionable ticker symbol (e.g. SPY, AAPL, NVDA)"
    )
    window_group = parser.add_mutually_exclusive_group()
    window_group.add_argument(
        "--days",
        choices=["30", "90"],
        default=None,
        help="DTE window to compute: 30 or 90. Defaults to 30.",
    )
    window_group.add_argument(
        "--0dte",
        dest="dte_zero",
        action="store_true",
        help="Compute today's 0DTE expiration only, instead of a 30/90-day window.",
    )
    args = parser.parse_args()
    symbol = args.symbol.upper()

    if args.dte_zero:
        window_key = "0dte"
        min_dte, max_dte = 0, 0
    else:
        days = int(args.days) if args.days else 30
        window_key = str(days)
        min_dte, max_dte = 1, days

    window_label = "0DTE" if args.dte_zero else f"DTE {min_dte}-{max_dte}"
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    print(f"OI vs Churn Report — {symbol}  ({window_label})\n")

    spot, is_direct_index = get_spot(symbol, today_str)
    print(f"Spot: ${spot:.2f}\n")

    raw_chain = get_chain(symbol, today_str, max_dte, is_direct_index)
    today_snap = parse_chain(raw_chain, min_dte, max_dte)
    print(f"  {len(today_snap)} contracts in range\n")

    history = load_history(symbol)
    is_intraday = window_key == "0dte"

    if is_intraday:
        now_ts = now.strftime("%H:%M:%S")
        prior = latest_prior_intraday(history, today_str, now_ts)
    else:
        prior = latest_prior_session(history, today_str, window_key)

    if prior is None:
        if is_intraday:
            save_intraday(symbol, history, today_str, now_ts, today_snap)
            print("No earlier snapshot from today found — this run establishes the baseline.")
            print(f"State saved -> {state_path(symbol)}")
            print("Run again later today (e.g. after lunch) to see the intraday OI/churn split.")
        else:
            save_today(symbol, history, today_str, window_key, today_snap)
            print(f"No prior-session snapshot found for window '{window_key}' — this run establishes the baseline.")
            print(f"State saved -> {state_path(symbol)}")
            print("Run again on a later session (same window) to see the OI/churn split.")
        return

    prior_label, prior_snap = prior
    if is_intraday:
        print(f"Comparing now ({now_ts}) vs earlier today ({prior_label})\n")
    else:
        print(f"Comparing {today_str} vs prior session {prior_label}  (window: {window_key})\n")

    rows = compute_churn(today_snap, prior_snap, incremental_volume=is_intraday)
    if not rows:
        print(
            "No overlapping contracts between today and the prior snapshot "
            "(chain window may have shifted) — nothing to compare."
        )
    else:
        ts = now.strftime("%Y%m%d_%H%M%S")
        out_path = csv_path(symbol, window_key, ts)
        save_csv(out_path, rows)
        print(f"Per-strike churn ({len(rows)} contracts) saved to {out_path}\n")

        calls = [r for r in rows if r["type"] == "call"]
        puts = [r for r in rows if r["type"] == "put"]
        near = [r for r in rows if r["dte"] <= NEAR_DTE]
        far = [r for r in rows if r["dte"] > NEAR_DTE]

        print_table(
            [
                bucket_row("Calls", bucket_summary(calls)),
                bucket_row("Puts", bucket_summary(puts)),
                bucket_row(f"Near (<={NEAR_DTE}d)", bucket_summary(near)),
                bucket_row(f"Far (>{NEAR_DTE}d)", bucket_summary(far)),
                bucket_row("Total", bucket_summary(rows)),
            ]
        )

    if is_intraday:
        save_intraday(symbol, history, today_str, now_ts, today_snap)
    else:
        save_today(symbol, history, today_str, window_key, today_snap)
    print(f"\nState saved -> {state_path(symbol)}")

    print("\nDone.")


if __name__ == "__main__":
    main()
