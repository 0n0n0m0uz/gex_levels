import argparse

import pandas as pd
from rich import box
from rich.console import Console
from rich.measure import Measurement
from rich.table import Table

from gex_levels.config import HISTORY_DIR

console = Console(force_terminal=True)


def _format_cell(column, value):
    if isinstance(value, float):
        if column in ("net_gex", "net_dex"):
            return f"{value:,.0f}"
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _print_df(df, title):
    table = Table(title=title, box=box.ROUNDED, header_style="bold cyan", title_style="bold yellow")
    for column in df.columns:
        table.add_column(column, justify="right" if pd.api.types.is_numeric_dtype(df[column]) else "left")
    for _, row in df.iterrows():
        table.add_row(*(_format_cell(column, row[column]) for column in df.columns))
    # Render at the table's natural (unshrunk) width instead of the detected
    # terminal width, so rich never truncates a column's content — wide
    # tables just run off the right edge for the terminal to wrap/scroll.
    # Console.print(width=...) clamps to min(width, self.width), so that
    # alone can't widen past the terminal — a dedicated wider Console is
    # needed instead.
    unconstrained = console.options.update(max_width=100_000)
    natural_width = Measurement.get(console, unconstrained, table).maximum
    wide_console = Console(force_terminal=True, width=natural_width)
    wide_console.print(table)


def list_symbols():
    if not HISTORY_DIR.exists():
        console.print(f"[red]No history dir at {HISTORY_DIR}[/red]")
        return
    table = Table(title="Saved History", box=box.ROUNDED, header_style="bold cyan", title_style="bold yellow")
    table.add_column("Symbol")
    table.add_column("Chain Snapshots", justify="right")
    table.add_column("Date Range")
    table.add_column("Summary")
    for symbol_dir in sorted(HISTORY_DIR.iterdir()):
        if not symbol_dir.is_dir():
            continue
        dates = sorted(p.stem for p in (symbol_dir / "chain").glob("*.parquet")) \
            if (symbol_dir / "chain").exists() else []
        has_summary = (symbol_dir / "summary.parquet").exists()
        table.add_row(
            symbol_dir.name,
            str(len(dates)),
            f"{dates[0]} .. {dates[-1]}" if dates else "-",
            "[green]yes[/green]" if has_summary else "[dim]no[/dim]",
        )
    console.print(table)


SUMMARY_CORE_COLUMNS = [
    "date", "tenor", "underlying", "gex_regime", "gamma_flip", "hvl",
    "call_wall", "put_wall", "net_gex", "net_dex", "dex_regime",
]


def view_summary(symbol, tenor=None, show_all=False):
    path = HISTORY_DIR / symbol / "summary.parquet"
    if not path.exists():
        console.print(f"[red]No summary file at {path}[/red]")
        return
    df = pd.read_parquet(path)
    if tenor is not None:
        df = df[df["tenor"] == int(tenor)]
    df = df.sort_values(["date", "tenor"])
    if df.empty:
        console.print("[dim]No matching rows[/dim]")
        return
    if not show_all:
        df = df[SUMMARY_CORE_COLUMNS]
    _print_df(df, f"{symbol} — Daily Summary")


def view_chain(symbol, date, option_type=None, expiration=None, sort=None, top=None):
    path = HISTORY_DIR / symbol / "chain" / f"{date}.parquet"
    if not path.exists():
        console.print(f"[red]No chain snapshot at {path}[/red]")
        return
    df = pd.read_parquet(path)
    if option_type is not None:
        df = df[df["option_type"] == option_type]
    if expiration is not None:
        df = df[df["expiration"] == expiration]
    if sort is not None:
        df = df.sort_values(sort, ascending=False)
    if top is not None and top > 0:
        # cap each option type separately (10 calls + 10 puts), not the
        # combined total, unless --type already narrowed it to one side
        if option_type is None:
            df = df.groupby("option_type", group_keys=False).head(top)
        else:
            df = df.head(top)
    if df.empty:
        console.print("[dim]No matching rows[/dim]")
        return
    _print_df(df, f"{symbol} — Chain Snapshot {date}")


def main():
    parser = argparse.ArgumentParser(description="View saved GEX history Parquet files")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List symbols with saved history")

    summary_parser = subparsers.add_parser("summary", help="View a symbol's daily summary history")
    summary_parser.add_argument("symbol")
    summary_parser.add_argument("--tenor", choices=["30", "90"], default=None)
    summary_parser.add_argument("--all", dest="show_all", action="store_true",
                                 help="show every column instead of the core level set")

    chain_parser = subparsers.add_parser("chain", help="View a symbol's raw chain snapshot for one day")
    chain_parser.add_argument("symbol")
    chain_parser.add_argument("date", help="YYYY-MM-DD")
    chain_parser.add_argument("--type", dest="option_type", choices=["call", "put"], default=None)
    chain_parser.add_argument("--expiration", default=None)
    chain_parser.add_argument("--sort", choices=["strike", "open_interest", "volume", "implied_vol"], default=None)
    chain_parser.add_argument("--top", type=int, default=10,
                               help="rows per option type to show (default 10); use 0 for no limit")

    args = parser.parse_args()

    if args.command == "list":
        list_symbols()
    elif args.command == "summary":
        view_summary(args.symbol, tenor=args.tenor, show_all=args.show_all)
    elif args.command == "chain":
        view_chain(
            args.symbol,
            args.date,
            option_type=args.option_type,
            expiration=args.expiration,
            sort=args.sort,
            top=args.top,
        )


if __name__ == "__main__":
    main()
