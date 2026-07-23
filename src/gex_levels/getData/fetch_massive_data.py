# ---------------------------------------------------------------------------
# Data source: Massive.com (live OI, greeks, IV)
# ---------------------------------------------------------------------------

def fetch_massive(today_str, etf="SPY"):
    """Fetch ETF spot + 0DTE chain from Massive.com. Returns (spot, chain)."""
    from massive import RESTClient

    client = RESTClient(api_key=MASSIVE_KEY)
    snapshots = list(client.list_snapshot_options_chain(
        etf, params={"expiration_date": today_str},
    ))

    if not snapshots:
        return None, []

    # Spot price from first option's underlying asset
    spot = None
    for snap in snapshots:
        if snap.underlying_asset and snap.underlying_asset.price:
            spot = float(snap.underlying_asset.price)
            break
    if not spot:
        raise ValueError("Massive: no underlying price in snapshot")

    normalized = []
    for opt in snapshots:
        details = opt.details
        if not details or not details.strike_price:
            continue

        day = opt.day or type("D", (), {"volume": 0})()
        greeks_obj = opt.greeks

        # Convert greeks object to dict for downstream compat (greeks.get("gamma"))
        greeks_dict = None
        if greeks_obj:
            greeks_dict = {
                "delta": greeks_obj.delta,
                "gamma": greeks_obj.gamma,
                "theta": greeks_obj.theta,
                "vega": greeks_obj.vega,
            }

        normalized.append({
            "strike": float(details.strike_price),
            "open_interest": int(opt.open_interest or 0),
            "volume": int(day.volume or 0),
            "option_type": (details.contract_type or "").lower(),
            "implied_volatility": float(opt.implied_volatility or 0),
            "greeks": greeks_dict,
        })

    return spot, normalized