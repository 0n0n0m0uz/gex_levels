"""
gex_daily.py - Daily GEX level calculator and shared library

The Orchestration file main.py initiates 4 tasks:
1. Compute Gex Levels
2. Output Data to a Json file
3. Output data to the terminal for convenience and for pasting into Pinescript
4. Checks if the debug flag is turned T/F in debug.py and prints extra verbose info to terminal

"""

# Import Submodules
from gex_levels.cli.cli import parse_args
from gex_levels.config import DEFAULT_SYMBOLS, OUTPUT_DIR
from gex_levels.gex.gex_compute import compute_gex_levels
from gex_levels.gex.zero_dte_gex_compute import compute_gex_levels_0dte
from gex_levels.outputs.output_gex_file import write_gex_file
from gex_levels.outputs.zero_dte_output_gex_file import write_gex_file_0dte
from gex_levels.outputs.zero_dte_pinescript_output import print_pinescript_block_0dte
from gex_levels.outputs.pinescript_output import print_pinescript_block
from gex_levels.outputs.historical_store import save_daily_summary
from gex_levels.outputs.gamma_exposure_chart import print_gamma_exposure_chart
from debug.debug_hub import hub

# External Modules
from rich.console import Console
#from rich.rule import Rule
console = Console(force_terminal=True)


# Setup of .env file to hold API keys.  Make sure to add to .gitignore and remove from all scripts so they are not on a public forum.
from dotenv import load_dotenv
load_dotenv()

####################################################################################################################################

def main():

    # Fires up the CLI plumbing
    args, windows = parse_args()

    # Gets the Symbols passed to CLI
    symbols = (
        [s.upper() for s in args.symbols] if args.symbols else list(DEFAULT_SYMBOLS)
    )

    # --- Execution Logic to split into 0DTE vs Daily track---
    if args.dte_zero:
        # 0DTE is active: ONLY use symbol, ignore everything else (--days is
        # meaningless for 0DTE — there's only one window, today's expiration)
        if len(symbols) > 1 and args.index:
            print("Warning: --index is ignored when multiple symbols are given.")
            args.index = None

        print(f"0DTE GEX Calculator -- {len(symbols)} symbol(s)\n")

        for symbol in symbols:
            try:
                console.print(
                    f"[bold italic grey42]...Downloading {symbol} 0DTE options chain...[/bold italic grey42]"
                )
                data = compute_gex_levels_0dte(symbol, index_ticker_override=args.index)
                # tenor=0 (int, not "0dte") — summary.parquet's tenor column is
                # already int64 from the daily 30/90 rows; 0 is reserved/unused
                # by the daily path (main.py's loop skips w == 0), so it's a
                # safe sentinel that keeps the column's dtype homogeneous.
                save_daily_summary(symbol, data["timestamp"][:10], 0, data)
                write_gex_file_0dte(data)
                print_pinescript_block_0dte(data)

                print(
                    f"  Gamma Flip: {data['gamma_flip']:.2f}  "
                    f"Call Wall: {data['call_wall']:.2f}  "
                    f"Put Wall: {data['put_wall']:.2f}  "
                    f"({data['gex_regime']})"
                )
                print()

                if not args.no_gamma_chart:
                    print_gamma_exposure_chart(
                        data["gex_profile"], data["underlying"], data["gamma_flip"],
                        data["call_wall"], data["put_wall"], symbol, "0DTE",
                    )
            except Exception:
                import traceback
                traceback.print_exc()

        print(f"Done. Files in {OUTPUT_DIR}")

    else:


        # Standard logic: honor --days, --strike, and any other flags
        print(f"Running standard logic for symbol: {symbols}")
        # Call your standard function here: run_standard_pipeline(symbol=args.symbol, days=args.days, strike=args.strike)

        if len(symbols) > 1 and args.index:
            print("Warning: --index is ignored when multiple symbols are given.")
            args.index = None

        print(f"GEX Level Calculator -- {len(symbols)} symbol(s)\n")

        for symbol in symbols:
            try:
                #print(f"[{symbol}] — downloading options chain...")
                console.print(
                    f"[bold italic grey42]...Downloading {symbol} options chain...[/bold italic grey42]"
                )
                data = {}
                for w in windows:
                    console.print(
                        f"[bold italic grey42]...Computing {w}-day window for {symbol}...[/bold italic grey42]"
                    )
                    if w == 0:
                        # Skip 0, or handle it with custom logic if needed
                        # data[w] = compute_gex_levels(
                        #     symbol,
                        #     max_dte=w,
                        #     index_ticker_override=args.index,

                        continue
                    # Task 1
                    data[w] = compute_gex_levels(
                        symbol,
                        max_dte=w,
                        index_ticker_override=args.index,
                    )
                    save_daily_summary(symbol, data[w]["timestamp"][:10], w, data[w])

                    # Task 2
                    write_gex_file(data[w], w)

                # Task 3
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
                        f"({d['gex_regime']})"
                    )

                print()

                if not args.no_gamma_chart:
                    for w in (30, 90):
                        if w not in data:
                            continue
                        d = data[w]
                        print_gamma_exposure_chart(
                            d["gex_profile"], d["underlying"], d["gamma_flip"],
                            d["call_wall"], d["put_wall"], symbol, f"{w}d",
                        )

            except Exception:
                import traceback
                traceback.print_exc()
            #except Exception as e:
            #    print(f"  Error: {e}\n")

        print(f"Done. Files in {OUTPUT_DIR}")

        # Task 4 - Turn Debug printing OFF / ON in debug_hub.py
        hub.dump()


if __name__ == "__main__":
    main()
