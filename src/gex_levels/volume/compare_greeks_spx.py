"""
compare_greeks_spx.py - Compare Schwab pre-computed greeks vs BS-calculated greeks for SPY

For near-ATM strikes, prints Schwab delta/gamma alongside our Black-Scholes values
using the same IV and spot so you can see the divergence.

Usage:
    python volume/compare_greeks_spx.py
"""

import os
import json
import base64
from datetime import datetime, timedelta


import requests
import yfinance as yf
import numpy as np
from scipy.stats import norm
from gex_levels.config import RISK_FREE_RATE
from gex_levels.auth.api_auth import SCHWAB_TOKEN_PATH as SCHWAB_TOKEN

from dotenv import load_dotenv

load_dotenv()

SCHWAB_CLIENT_ID = os.getenv("SCHWAB_CLIENT_ID")
SCHWAB_CLIENT_SECRET = os.getenv("SCHWAB_CLIENT_SECRET")

ETF = "SPY"
ATM_BAND = 0.03  # show strikes within ±3% of spot
NEAR_EXPIRY_DAYS = 30  # only look at expirations within 30 days
DIVIDEND_YIELD = (
    0.012  # approx SPY trailing dividend yield (continuous-yield approximation)
)


def get_spot():
    hist = yf.Ticker(ETF).history(period="1d", interval="1m")
    return float(hist["Close"].iloc[-1]) if not hist.empty else None


def bs_delta_q(S, K, T, r, q, sigma, is_call=True):
    """Black-Scholes delta with a continuous dividend yield q."""
    d1 = (np.log(S / K) + (r - q + sigma**2 / 2) * T) / (sigma * np.sqrt(T))
    disc_q = np.exp(-q * T)
    return disc_q * norm.cdf(d1) if is_call else disc_q * (norm.cdf(d1) - 1.0)


def bs_gamma_q(S, K, T, r, q, sigma):
    """Black-Scholes gamma with a continuous dividend yield q."""
    d1 = (np.log(S / K) + (r - q + sigma**2 / 2) * T) / (sigma * np.sqrt(T))
    return np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))


def _refresh_schwab_token(token_data):
    """Refresh an expired Schwab access token using the stored refresh_token."""
    auth_str = base64.b64encode(
        f"{SCHWAB_CLIENT_ID}:{SCHWAB_CLIENT_SECRET}".encode()
    ).decode()
    resp = requests.post(
        "https://api.schwabapi.com/v1/oauth/token",
        headers={
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": token_data["token"]["refresh_token"],
        },
        timeout=20,
    )
    resp.raise_for_status()
    new_token = resp.json()
    if "refresh_token" not in new_token:
        new_token["refresh_token"] = token_data["token"]["refresh_token"]
    token_data["token"] = new_token
    with open(SCHWAB_TOKEN, "w") as f:
        json.dump(token_data, f)
    return new_token["access_token"]


def fetch_schwab_chain():
    with open(SCHWAB_TOKEN) as f:
        token_data = json.load(f)

    today = datetime.now()
    to_date = today + timedelta(days=NEAR_EXPIRY_DAYS)

    def _request(access_token):
        return requests.get(
            "https://api.schwabapi.com/marketdata/v1/chains",
            params={
                "symbol": ETF,
                "range": "NTM",
                "strikeCount": 40,
                "fromDate": today.strftime("%Y-%m-%d"),
                "toDate": to_date.strftime("%Y-%m-%d"),
            },
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=60,
        )

    resp = _request(token_data["token"]["access_token"])
    if resp.status_code == 401:
        access_token = _refresh_schwab_token(token_data)
        resp = _request(access_token)
    if resp.status_code != 200:
        raise RuntimeError(f"Schwab API returned {resp.status_code}: {resp.text}")
    return resp.json()


def main():
    print(f"Greeks Comparison — Schwab vs Black-Scholes ({ETF})\n")

    spot = get_spot()
    print(f"Spot: ${spot:.2f}\n")

    data = fetch_schwab_chain()
    now = datetime.now()
    rfr = RISK_FREE_RATE

    print(
        f"{'Exp':>12} {'Type':>5} {'Strike':>8} {'DTE':>4} "
        f"{'SCH_Delta':>10} {'BS_Delta':>10} {'D_Diff':>8} "
        f"{'SCH_Gamma':>10} {'BS_Gamma':>10} {'G_Diff':>8}"
    )
    print("-" * 100)

    for map_key, opt_type in [("callExpDateMap", "call"), ("putExpDateMap", "put")]:
        for exp_key, strikes in data.get(map_key, {}).items():
            exp_str = exp_key.split(":")[0]
            exp_dt = datetime.strptime(exp_str, "%Y-%m-%d").replace(
                hour=16
            )  # options expire at market close
            dte = (datetime.strptime(exp_str, "%Y-%m-%d") - now).days
            if dte < 1 or dte > NEAR_EXPIRY_DAYS:
                continue
            days_remaining = (exp_dt - now).total_seconds() / 86400
            T = max(days_remaining, 0.5) / 365.0

            for strike_str, contracts in strikes.items():
                for opt in contracts:
                    strike = float(opt.get("strikePrice", 0))
                    if not (spot * (1 - ATM_BAND) <= strike <= spot * (1 + ATM_BAND)):
                        continue

                    iv = float(opt.get("volatility") or 0) / 100.0
                    sch_delta = opt.get("delta")
                    sch_gamma = opt.get("gamma")

                    if iv <= 0 or sch_delta is None or sch_gamma is None:
                        continue

                    sch_delta = float(sch_delta)
                    sch_gamma = float(sch_gamma)
                    is_call = opt_type == "call"

                    bs_d = float(
                        bs_delta_q(
                            spot, strike, T, rfr, DIVIDEND_YIELD, iv, is_call=is_call
                        )
                    )
                    bs_g = float(bs_gamma_q(spot, strike, T, rfr, DIVIDEND_YIELD, iv))

                    print(
                        f"{exp_str:>12} {opt_type:>5} {strike:>8.1f} {dte:>4} "
                        f"{sch_delta:>10.4f} {bs_d:>10.4f} {sch_delta - bs_d:>+8.4f} "
                        f"{sch_gamma:>10.6f} {bs_g:>10.6f} {sch_gamma - bs_g:>+8.6f}"
                    )


if __name__ == "__main__":
    main()
