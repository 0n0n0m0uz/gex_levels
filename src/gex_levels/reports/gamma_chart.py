"""
gamma_chart.py - Standalone per-strike gamma exposure bar chart.

Runs the same GEX pipeline as `gex` (compute_gex_levels / compute_gex_levels_0dte)
for a single symbol/window and prints only the chart — no JSON/pinescript files
are written, unlike a normal `gex` run.

Usage:
    uv run gamma-chart SPY                 # --days 30 (default)
    uv run gamma-chart SPX --days 90
    uv run gamma-chart SPX --0dte
    uv run gamma-chart SPY --rows 20
"""

import argparse

from dotenv import load_dotenv

load_dotenv()

from gex_levels.gex.gex_compute import compute_gex_levels
from gex_levels.gex.zero_dte_gex_compute import compute_gex_levels_0dte
from gex_levels.outputs.gamma_exposure_chart import print_gamma_exposure_chart


def main():
    parser = argparse.ArgumentParser(
        description="Render a per-strike net gamma exposure bar chart for a single symbol.",
        epilog="Examples:\n"
        "  uv run gamma-chart SPY\n"
        "  uv run gamma-chart SPX --days 90\n"
        "  uv run gamma-chart SPX --0dte",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("symbol", help="Ticker symbol (e.g. SPY, SPX, AAPL)")
    window_group = parser.add_mutually_exclusive_group()
    window_group.add_argument(
        "--days", choices=["30", "90"], default=None,
        help="DTE window: 30 or 90. Defaults to 30.",
    )
    window_group.add_argument(
        "--0dte", dest="dte_zero", action="store_true",
        help="Chart today's 0DTE expiration instead of a 30/90-day window.",
    )
    parser.add_argument(
        "--rows", type=int, default=None,
        help="Max strikes to display, centered on spot (default 40).",
    )
    args = parser.parse_args()
    symbol = args.symbol.upper()

    if args.dte_zero:
        data = compute_gex_levels_0dte(symbol)
        window_label = "0DTE"
    else:
        days = int(args.days) if args.days else 30
        data = compute_gex_levels(symbol, max_dte=days)
        window_label = f"{days}d"

    chart_kwargs = {"max_rows": args.rows} if args.rows else {}
    print_gamma_exposure_chart(
        data["gex_profile"], data["underlying"], data["gamma_flip"],
        data["call_wall"], data["put_wall"], symbol, window_label,
        **chart_kwargs,
    )


if __name__ == "__main__":
    main()
