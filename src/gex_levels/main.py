"""
gex_daily.py - Daily GEX level calculator and shared library
"""

## Standard Library Packages
import argparse

# External Modules

# Import Submodules
from gex_levels.config import DEFAULT_SYMBOLS, OUTPUT_DIR
from gex_levels.gex.gex_compute import compute_gex_levels
from gex_levels.outputs.output_gex_file import write_gex_file
from gex_levels.outputs.pinescript_output import print_pinescript_block



from debug.debug_hub import hub

# Setup of .env file to hold API keys.  Make sure to add to .gitignore and remove from all scripts so they are not on a public forum.
from dotenv import load_dotenv
load_dotenv()

####################################################################################################################################

def main():

    parser = argparse.ArgumentParser(
        description="Compute daily GEX levels for any symbol — index (direct Schwab "
        "chain) or equity/ETF (Schwab, yfinance fallback). Whatever you "
        "type is what gets fetched, no silent substitution.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python gex_daily.py                    # SPX + NDX (default)
  python gex_daily.py SPX                # real $SPX index chain, direct from Schwab
  python gex_daily.py NDX                # real $NDX index chain, direct from Schwab
  python gex_daily.py VIX                # real $VIX index chain (approx: spot VIX as BS input)
  python gex_daily.py SPY                # real SPY ETF chain — not converted to SPX
  python gex_daily.py QQQ                # real QQQ ETF chain — not converted to NDX
  python gex_daily.py AAPL               # any stock, own price space
  python gex_daily.py IWM --index ^RUT   # manual ratio conversion for tickers with no
                                         # native Schwab index chain
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
        "--vix",
        metavar="TICKER",
        default=None,
        help="Volatility index ticker for expected-move data (e.g. ^RVX). "
        "Only applies when a single symbol is given.",
    )
    parser.add_argument(
        "--days",
        metavar="{30,90,30,90}",
        default="30",
        help="DTE window(s) to compute: 30, 90, or 30,90 for both. Defaults to 30.",
    )

    args = parser.parse_args()


    symbols = (
        [s.upper() for s in args.symbols] if args.symbols else list(DEFAULT_SYMBOLS)
    )

    try:
        # reverse=True puts 90 before 30 when both are requested — required so the
        # Schwab chain cache (keyed only on symbol+date, not max_dte) gets populated
        # with the wider window first; the 30d pass then reuses and filters it down.
        windows = sorted({int(d.strip()) for d in args.days.split(",")}, reverse=True)

    except ValueError:
        parser.error(f"--days must be 30, 90, or 30,90 (got: {args.days!r})")
    if not windows or any(w not in (30, 90) for w in windows):
        parser.error(f"--days must be 30, 90, or 30,90 (got: {args.days!r})")

    if len(symbols) > 1 and (args.index or args.vix):
        print("Warning: --index and --vix are ignored when multiple symbols are given.")
        args.index = None
        args.vix = None

    print(f"GEX Level Calculator -- {len(symbols)} symbol(s)\n")

    for symbol in symbols:
        try:
            print(f"[{symbol}] — downloading options chain...")
            data = {}
            for w in windows:
                print(f"[{symbol}] — computing {w}-day window...")
                data[w] = compute_gex_levels(
                    symbol,
                    max_dte=w,
                    index_ticker_override=args.index,
                    vix_ticker_override=args.vix,
                )
            write_gex_file(data.get(30))
            write_gex_file(data.get(90))

            print_pinescript_block(
                data30=data.get(30),
                data90=data.get(90),
            )

            # Print 30-day first, then 90-day if they exist
            for w in (30, 90):
                if w not in data:
                    continue

                d = data[w]
                print(
                    f"  [{w}d] Gamma Flip: {d['gamma_flip']:.2f}  "
                    f"Call Wall: {d['call_wall']:.2f}  "
                    f"Put Wall: {d['put_wall']:.2f}  "
                    f"({d['regime']})"
                )

            print()

        except Exception:
            import traceback
            traceback.print_exc()
        #except Exception as e:
        #    print(f"  Error: {e}\n")

    print(f"Done. Files in {OUTPUT_DIR}")

    # PRINT IT TO THE TERMINAL
    print("\n--- DEBUG VARIABLES COLLECTED ---")
    for key, value in hub.variables.items():
        print(f"{key}: {value}")
    print("---------------------------------\n")




if __name__ == "__main__":
    main()
