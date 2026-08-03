"""
cli.py - Command-line argument parsing for gex_levels
"""

import argparse


def build_parser():
    parser = argparse.ArgumentParser(
        description="Compute daily GEX levels for any symbol — index (direct Schwab "
        "chain) or equity/ETF (Schwab, yfinance fallback). Whatever you "
        "type is what gets fetched, no silent substitution.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python gex_daily.py                    # SPX + NDX (default)
  python gex_daily.py SPX                # real $SPX index chain, direct from Schwab
  python gex_daily.py AAPL               # any stock, own price space
  python gex_daily.py IWM --index ^RUT   # manual ratio conversion for tickers with
  python gex_daily.py SPX NDX VIX SPY    # multiple symbols in one run
  python gex_daily.py SPX --days 90      # 90-day window only
  python gex_daily.py SPX --days 30,90   # both windows in one run
        """,
    )
    parser.add_argument(
        "symbols",
        nargs="*",
        metavar="SYMBOL",
        help="One or more symbols (e.g. SPX NDX VIX SPY QQQ AAPL). "
        "Defaults to SPX and NDX when omitted.",
    )
    parser.add_argument(
        "--index",
        metavar="TICKER",
        default=None,
        help="Index ticker for price-space conversion (e.g. ^RUT). "
        "Only applies when a single symbol is given; ignored for multi-symbol runs.",
    )
    parser.add_argument(
        "--days",
        metavar="{30,90,30,90}",
        default="30",
        help="DTE window(s) to compute: 30, 90, or 30,90 for both. Defaults to 30.",
    )

    parser.add_argument(
        "--0dte",
        dest="dte_zero",
        action="store_true",
        help="Enable separate 0DTE processing logic.",
    )

    parser.add_argument(
        "--no-gamma-chart",
        dest="no_gamma_chart",
        action="store_true",
        help="Skip the per-strike gamma exposure bar chart printed at the end of each run.",
    )

    return parser


def parse_args():
    parser = build_parser()
    args = parser.parse_args()

    try:
        # reverse=True puts 90 before 30 when both are requested — required so the
        # Schwab chain cache (keyed only on symbol+date, not max_dte) gets populated
        # with the wider window first; the 30d pass then reuses and filters it down.
        windows = sorted({int(d.strip()) for d in args.days.split(",")}, reverse=True)
    except ValueError:
        parser.error(f"--days must be 0, 30, 90, or 30,90 (got: {args.days!r})")
    if not windows or any(w not in (0, 30, 90) for w in windows):
        parser.error(f"--days must be 0, 30, 90, or 30,90 (got: {args.days!r})")

    return args, windows
