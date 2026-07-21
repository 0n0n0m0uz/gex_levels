from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

console = Console()


def print_gex_summary(data):
    """
    Pretty terminal output for GEX calculations using Rich.

    Expects the dictionary returned by compute_gex_levels().
    """

    symbol = data["symbol"]
    underlying = data["underlying"]
    timestamp = data["timestamp"][:10]

    # Optional fields
    risk_free_rate = data.get("risk_free_rate", 0)
    exp_count = data.get("exp_count", 0)
    calls = data.get("calls", [])
    puts = data.get("puts", [])
    tau = data.get("tau", 0)

    net_dex = data["net_dex"]
    dex_regime = data["dex_regime"]

    border_color = "red" if net_dex < 0 else "green"

    console.print()

    console.print(
        Panel(
            f"[bold]{symbol} GEX Summary[/bold]\n"
            f"Date: {timestamp}\n"
            f"Underlying: {underlying:.2f}",
            border_style=border_color,
        )
    )

    console.print(Rule("[bold cyan]Market Data[/bold cyan]"))

    console.print(
        f"  Risk-Free Rate   [green]{risk_free_rate:.2%}[/green] (SOFR)"
    )
    console.print(f"  Expirations      {exp_count}")
    console.print(f"  Calls            {len(calls):,}")
    console.print(f"  Puts             {len(puts):,}")
    console.print(f"  Tau              {tau:.0f} days")

    console.print(Rule("[bold magenta]Dealer Positioning[/bold magenta]"))

    dex_color = "red" if net_dex < 0 else "green"

    console.print(
        f"  Net DEX          "
        f"[{dex_color}]{net_dex:,.0f}[/{dex_color}] "
        f"({dex_regime})"
    )

    console.print(
        f"  CPR Raw          {data['cpr_raw']:.4f}"
    )
    console.print(
        f"  CPR Notional     {data['cpr_notl']:.4f}"
    )

    console.print(Rule("[bold blue]Volatility[/bold blue]"))

    console.print(
        f"  ATM Skew Slope   {data.get('skew_slope', 0):.6f}"
    )
    console.print(
        f"  R²               {data.get('r2', 0):.3f}"
    )
    console.print(
        f"  Alpha            {data.get('alpha', 0):.2f}"
    )

    console.print(Rule("[bold yellow]GEX Levels[/bold yellow]"))

    console.print(
        f"  Gamma Flip       [yellow]{data['gamma_flip']:.2f}[/yellow]"
    )
    console.print(
        f"  HVL              [yellow]{data['hvl']:.2f}[/yellow]"
    )
    console.print(
        f"  Vol Trigger      [yellow]{data['vol_trigger']:.2f}[/yellow]"
    )

    profile = data.get("gex_profile", [])

    console.print(
        f"  GEX Profile      {len(profile)} strikes"
    )

    console.print()