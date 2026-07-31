from rich.console import Console
from rich.rule import Rule

console = Console(force_terminal=True)


def print_market_data_0dte(data):
    """0DTE analogue of rich_terminal_output.print_market_data() — same
    layout, with the "Tau" line (DTE-decay time constant — meaningless for
    a same-day expiration) swapped for "Open Ratio" (the volume-into-OI
    weighting collect_chain_0dte() actually uses instead).

    data: spot, rf_rate_msg, num_expirations, calls, puts, open_ratio
    """
    console.print(Rule("[bold green]Market Data (0DTE)[/bold green]"))
    console.print()
    console.print(f"  {'Spot':<22} ${data['spot']:.2f}")
    console.print(f"{data['rf_rate_msg']}")
    console.print(f"  {'Expirations':<22} {data['num_expirations']}")
    console.print(f"  {'Calls':<22} {len(data['calls']):,}")
    console.print(f"  {'Puts':<22} {len(data['puts']):,}")
    console.print(f"  {'Open Ratio':<22} {data['open_ratio']:.2f}")
