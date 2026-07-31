from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

console = Console(force_terminal=True)


def print_market_data(data):
    """data: spot, rf_rate_msg, num_expirations, calls, puts, tau"""
    console.print(Rule("[bold green]Market Data[/bold green]"))
    console.print()   # insert a blank row
    console.print(f"  {'Spot':<22} ${data['spot']:.2f}")
    console.print(f"{data['rf_rate_msg']}")  # This has a different format because the rate is calc in different module
    console.print(f"  {'Expirations':<22} {data['num_expirations']}")
    console.print(f"  {'Calls':<22} {len(data['calls']):,}")
    console.print(f"  {'Puts':<22} {len(data['puts']):,}")
    console.print(f"  {'Tau':<22} {data['tau']:.0f}-days")


def print_dealer_positioning(data):
    """data: dex_color, net_dex, dex_regime, pcr_raw, pcr_notional"""
    console.print(Rule("[bold magenta]Dealer Positioning[/bold magenta]"))
    console.print()
    console.print(
        f"  {'Net DEX':<22} "
        f"[{data['dex_color']}]${data['net_dex']:,.0f}[/{data['dex_color']}] "
        f"({data['dex_regime']})")
    console.print(f"  {'Put-Call Raw':<22} {data['pcr_raw']:.3f}")
    console.print(f"  {'Put-Call Notional':<22} {data['pcr_notional']:.3f}")
    console.print()


def print_volatility(data):
    """data: skew_slope, skew_r2, skew_alpha"""
    console.print(Rule("[bold blue]Volatility[/bold blue]"))
    console.print()
    console.print(f"  {'ATM Skew Slope':<22} {data['skew_slope']: .5f}")
    console.print(f"  {'R²':<22} {data['skew_r2']:.3f}")
    console.print(f"  {'Alpha':<22} {data['skew_alpha']:.2f}")
    console.print()


def print_gex_levels(data):
    """data: gamma_flip, call_wall, put_wall, hvl, vol_trigger, max_pain"""
    console.print(Rule("[bold yellow]GEX Levels[/bold yellow]"))
    console.print()

    levels = [
        ("Gamma Flip", data["gamma_flip"]),
        ("Call Wall", data["call_wall"]),
        ("Put Wall", data["put_wall"]),
        ("HVL", data["hvl"]),
        ("Vol Trigger", data["vol_trigger"]),
        ("Max Pain", data["max_pain"]),
    ]

    # Sort descending by price
    levels.sort(key=lambda x: x[1], reverse=True)

    # Build the text lines inside the block
    lines = [f"  {label:<22} ${val:,.2f}" for label, val in levels]
    content = "\n".join(lines)

    # Wrap it in a panel with a down arrow on the right side of the border
    console.print(Panel(content, box=box.ROUNDED, expand=False, title="[cyan]⬇[/cyan]", title_align="right"))


def print_gex_profile_and_hysteresis(data):
    """data: gex_profile, call_wall_held, prev_cw, raw_call_wall, put_wall_held, prev_pw, raw_put_wall"""
    gex_profile = data["gex_profile"]

    console.print()
    console.print(
        f"  GEX profile: [cyan]{len(gex_profile)}[/cyan] strikes "
        f"({sum(1 for _, g in gex_profile if g > 0)} call, "
        f"{sum(1 for _, g in gex_profile if g < 0)} put)"
    )

    if data["call_wall_held"]:
        print(
            f"  Call wall held at {data['prev_cw']:.2f} "
            f"(hysteresis — new candidate {data['raw_call_wall']:.2f} not 10%+ stronger)"
        )
    if data["put_wall_held"]:
        print(
            f"  Put wall held at {data['prev_pw']:.2f} "
            f"(hysteresis — new candidate {data['raw_put_wall']:.2f} not 10%+ stronger)"
        )


def print_footer():
    console.print()
    console.print()
    console.print(Rule(characters="═", style="bold dark_magenta"))

    # Prints two blank lines of space to terminal to separate the 30d and 90d data
    print("\n\n")
