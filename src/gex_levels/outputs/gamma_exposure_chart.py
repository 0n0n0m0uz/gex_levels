"""
gamma_exposure_chart.py - Per-strike net gamma exposure bar chart for the terminal.

Takes an already-computed gex_profile (list of (strike, net_gex) tuples, as
returned by compute_gex_levels()/compute_gex_levels_0dte() — net_gex is
call_gex + put_gex per strike, i.e. dollar gamma per 1% move) and renders a
diverging horizontal bar chart centered on a zero axis: red bars (net dealer
short gamma) grow left, green bars (net dealer long gamma) grow right, with
magnitude-based color intensity. Strikes near the spot/gamma-flip/wall levels
are annotated inline and the spot row is highlighted.
"""

from rich import box
from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

console = Console(force_terminal=True, width=100)

BAR_HALF_WIDTH = 24  # characters on each side of the zero axis
MAX_ROWS = 40  # cap displayed strikes so the chart fits one screen
OFF_CHART_TOLERANCE_PCT = 0.03  # if a key level's nearest shown strike is farther than this, footnote it instead of mismarking

# Sub-character block glyphs, one per eighth of a cell, for smoother bar tips
_PARTIAL_BLOCKS = " ▏▎▍▌▋▊▉"


def _fmt_gex(val):
    abs_val = abs(val)
    sign = "+" if val >= 0 else "-"
    if abs_val >= 1e9:
        return f"{sign}${abs_val / 1e9:.2f}B"
    elif abs_val >= 1e6:
        return f"{sign}${abs_val / 1e6:.1f}M"
    elif abs_val >= 1e3:
        return f"{sign}${abs_val / 1e3:.0f}K"
    return f"{sign}${abs_val:.0f}"


def _intensity_style(ratio, color):
    """ratio: this bar's magnitude as a fraction of the largest bar shown."""
    if ratio >= 0.66:
        return f"bold {color}"
    if ratio >= 0.33:
        return color
    return f"dim {color}"


def _nearest_strike(rows, level):
    return min((s for s, _ in rows), key=lambda s: abs(s - level))


def _select_strikes(gex_profile, spot, gamma_flip, call_wall, put_wall, max_rows):
    """Select strikes spanning at least [put_wall, call_wall] and gamma_flip
    (plus spot), so the key structural levels are always shown in context
    instead of silently falling outside a naive "nearest N to spot" window.
    Falls back to nearest-to-spot if that band is too narrow (thin chain),
    and subsamples evenly (while pinning the key levels) if it's too wide.
    """
    lower = min(put_wall, gamma_flip, spot) * 0.98
    upper = max(call_wall, gamma_flip, spot) * 1.02

    in_band = sorted(
        (p for p in gex_profile if lower <= p[0] <= upper),
        key=lambda p: p[0], reverse=True,
    )

    if len(in_band) < min(15, len(gex_profile)):
        nearest = sorted(gex_profile, key=lambda p: abs(p[0] - spot))[:max_rows]
        return sorted(nearest, key=lambda p: p[0], reverse=True)

    if len(in_band) <= max_rows:
        return in_band

    # Thin evenly, but always keep the strikes nearest each key level so
    # markers never end up pinned to a misleadingly distant row.
    keep_strikes = {_nearest_strike(in_band, lvl) for lvl in (spot, gamma_flip, call_wall, put_wall)}
    step = len(in_band) / max_rows
    thinned = {in_band[round(i * step)] for i in range(max_rows) if round(i * step) < len(in_band)}
    thinned |= {p for p in in_band if p[0] in keep_strikes}
    return sorted(thinned, key=lambda p: p[0], reverse=True)


def _bar_text(gex, max_abs):
    """Diverging bar for one strike: red fills leftward from center for
    negative net GEX, green fills rightward for positive, with magnitude-based
    color intensity (dim -> normal -> bold as the bar approaches max_abs).
    The growing (outer) tip gets eighth-block sub-character precision on the
    call/positive side, where Unicode's LEFT-n/8-BLOCK glyphs are the correct
    shape; the put/negative side rounds to the nearest whole block since
    Unicode has no equivalent full set of RIGHT-anchored partial glyphs."""
    magnitude = abs(gex) / max_abs * BAR_HALF_WIDTH
    ratio = abs(gex) / max_abs

    bar = Text()
    if gex >= 0:
        full = int(magnitude)
        partial = _PARTIAL_BLOCKS[round((magnitude - full) * 7)]
        style = _intensity_style(ratio, "green")
        bar.append(" " * BAR_HALF_WIDTH)
        bar.append("│", style="grey50")
        bar.append("█" * full + partial, style=style)
        bar.append(" " * (BAR_HALF_WIDTH - full - (1 if partial != " " else 0)))
    else:
        full = round(magnitude)
        style = _intensity_style(ratio, "red")
        bar.append(" " * (BAR_HALF_WIDTH - full))
        bar.append("█" * full, style=style)
        bar.append("│", style="grey50")
        bar.append(" " * BAR_HALF_WIDTH)
    return bar


def print_gamma_exposure_chart(
    gex_profile, spot, gamma_flip, call_wall, put_wall, symbol, window_label,
    *, max_rows=MAX_ROWS,
):
    console.print(Rule(f"[bold cyan]Gamma Exposure by Strike[/bold cyan] — [bold]{symbol}[/bold] ({window_label})", style="cyan"))
    console.print()

    if not gex_profile:
        console.print("  No strikes to chart.\n")
        return

    rows = _select_strikes(gex_profile, spot, gamma_flip, call_wall, put_wall, max_rows)
    max_abs = max(abs(g) for _, g in rows) or 1.0
    tolerance = spot * OFF_CHART_TOLERANCE_PCT

    def _marker_strike(level):
        nearest = _nearest_strike(rows, level)
        return nearest if abs(nearest - level) <= tolerance else None

    spot_strike = _marker_strike(spot)
    flip_strike = _marker_strike(gamma_flip)
    call_wall_strike = _marker_strike(call_wall)
    put_wall_strike = _marker_strike(put_wall)

    console.print(
        f"  Spot: [bold]${spot:,.2f}[/bold]   "
        f"Gamma Flip: ${gamma_flip:,.2f}   "
        f"Call Wall: [green]${call_wall:,.2f}[/green]   "
        f"Put Wall: [red]${put_wall:,.2f}[/red]"
    )
    console.print()

    bar_header = Text()
    bar_header.append("◄ PUT / DEALER SHORT".rjust(BAR_HALF_WIDTH + 1), style="dim red")
    bar_header.append(" " * 2)
    bar_header.append("CALL / DEALER LONG ►".ljust(BAR_HALF_WIDTH + 1), style="dim green")

    table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold grey70",
        pad_edge=False,
        expand=False,
        row_styles=None,
    )
    table.add_column("Strike", justify="right")
    table.add_column(bar_header, justify="left", no_wrap=True)
    table.add_column("Net GEX", justify="right")
    table.add_column("", justify="left", no_wrap=True)

    for strike, gex in rows:
        is_spot = strike == spot_strike
        strike_cell = Text(f"{strike:,.1f}", style="bold white" if is_spot else "")
        bar_cell = _bar_text(gex, max_abs)
        value_cell = Text(_fmt_gex(gex), style="bold" if is_spot else "")

        markers = []
        if is_spot:
            markers.append("[bold yellow]◄ SPOT[/bold yellow]")
        if strike == flip_strike:
            markers.append("[grey70]Γ Flip[/grey70]")
        if strike == call_wall_strike:
            markers.append("[bold green]Call Wall[/bold green]")
        if strike == put_wall_strike:
            markers.append("[bold red]Put Wall[/bold red]")
        marker_cell = Text.from_markup(" ".join(markers))

        table.add_row(
            strike_cell, bar_cell, value_cell, marker_cell,
            style="on grey19" if is_spot else None,
        )

    console.print(table)

    off_chart = []
    if flip_strike is None:
        off_chart.append(f"Gamma Flip ${gamma_flip:,.2f} (off displayed range)")
    if call_wall_strike is None:
        off_chart.append(f"[green]Call Wall ${call_wall:,.2f}[/green] (off displayed range)")
    if put_wall_strike is None:
        off_chart.append(f"[red]Put Wall ${put_wall:,.2f}[/red] (off displayed range)")
    if off_chart:
        console.print()
        console.print("  " + "   ".join(off_chart))

    console.print()
    console.print(
        "  [dim]Bar intensity scales with |net GEX| relative to the largest strike shown.[/dim]"
    )
    console.print()
