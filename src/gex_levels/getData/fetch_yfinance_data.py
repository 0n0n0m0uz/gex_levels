import os
import sys
from datetime import datetime

import numpy as np


from gex_levels.config import DTE_TAU_30, DTE_TAU_90


def collect_chain(raw, spot, max_dte, dte_tau=None):
    """
    This is the second step where business logic filtering is applied to the data and the raw native format is converted
    to separate numpy arrays for more efficient transformation and calculation of the Black Scholes formulas

    Build DTE-weighted options arrays from already-resolved chain data (see
    getData.fetch_spot.get_spot_and_chain for how `raw` is obtained).

    Returns (calls, puts, exp_count) where each array is Nx4:
    [strike, weighted_OI, T_years, implied_vol]

    Fixes vs original:
    - dte < 0 (not <=) so 0DTE is included and gets maximum decay weight
    - ±20% OTM filter (was ±30% — too wide, pollutes gamma profile with junk)
    - T floored at 0.5/365 so gamma doesn't blow up for same-day expiry
    - Chain downloaded once and reused for both 30d and 90d passes
    """
    if dte_tau is None:
        dte_tau = DTE_TAU_30 if max_dte <= 30 else DTE_TAU_90

    now = datetime.now()
    calls_list, puts_list = [], []
    exp_count = 0

    for exp_str, calls_df, puts_df in raw:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d")
        dte = (exp_date - now).days
        if dte < 0 or dte > max_dte:
            continue
        T = max(dte, 0.5) / 365.0  # floor at half-day to keep gamma finite
        dte_weight = np.exp(-dte / dte_tau)
        exp_count += 1

        for df, out_list in [(calls_df, calls_list), (puts_df, puts_list)]:
            mask = (
                (df["impliedVolatility"] > 0.001)
                & (df["openInterest"] > 0)
                & (df["strike"] > 0)
                & (df["strike"] > spot * 0.80)  # ±20% (was ±30%)
                & (df["strike"] < spot * 1.20)
            )
            for _, row in df[mask].iterrows():
                out_list.append(
                    [
                        row["strike"],
                        row["openInterest"] * dte_weight,
                        T,
                        row["impliedVolatility"],
                    ]
                )

    calls = np.array(calls_list) if calls_list else np.empty((0, 4))
    puts = np.array(puts_list) if puts_list else np.empty((0, 4))
    return calls, puts, exp_count