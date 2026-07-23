
It is a safe assumption what more than 50% of dealer positioning is selling options to retail investors.  It is possibly as high as 85% short positions.

## $\Delta$ Delta
Delta represents the exposure an option has to the equity market in terms of the direction of price movement of the underlying.

## $\Gamma$ - Gamma
Gamma represents the degree to which your exposure to the equity market is increasing or decreasing.
It is the convexity of the delta.
---
## ATM Skew Slope
The ATM skew slope (often referred to simply as the strike slope or skew slope around the money) measures the local steepness of the implied volatility (IV) curve right where the options are at-the-money.

Instead of looking at the overall slope from deep OTM puts to deep Otm calls, it isolates how fast implied volatility changes per unit of strike or delta at the exact center of the options chain.

## $R^2$

## $\tau$ - Tau (Time to Expiration)

Expressed in fraction of a year



Sophisticated investors will weight GEX by DTE because weighting by DTE 
normalizes time, transforming GEX from a simple structural calculation into an accurate gauge of **real-world market-maker hedging pressure**.

The Tau is used to weight which expirations contribute more to the gex calculation.
Because gamma approaches large numbers as expiration approaches those near term expirations can have an outsized influence on a longer terms gex calulation.
The Tau of 7 will artificially lower the influence of these options compared to later ones.

Obviously for a longer term gex horizon of 90 days the tau can be larger to place more weight on the expirations further into the future


## $\alpha$ - Alpha

Alpha is the y-intercept of the volatility model or the volatility predicted even when historical volatility is zero.
It can be interpreted as a sort of baseline volatility level
---
##  Gamma Flip

## Call Wall

The options call wall is the single strike where net call gamma is highest for a given underlying.

## Put Wall

The Put Wall is the strike with the largest net put gamma for a given underlying.

## HVL

The HVL marks the geographic midpoint or heavy concentration center of total market maker exposure across the board. In many profiles, the HVL sits higher up in the strike range because open interest and absolute gamma tend to build heavily in the upper call structure.

## VOL Trigger

The lowest qualifying call-side strike with meaningful positive GEX at or above the gamma flip.

This marks the level where call dealer hedging (buy pressure) kicks in  meaningfully on the upside.  Often sits between Gamma Flip and Call Wall.





# Net Gex

To compare one days net gex vs another will signal something about the relative x of that day vs others.
Net Gex is less helpful for longer periods, but it probably makes sense to compare the monthly opex cycle to another

# Historical Option Chain Data

Where can I get historical option data?

## Volatility Risk Premium

A daily metric which calculates the daily historical volatility compared to the expected volatility based on IV.

ATR greater than 1 std deviation comapred to previous x days?

Maybe this is a leading indicator about a reversal or breakout trend??

---
**Practical ranking of what to track:**

For day-over-day relative change tracking, the best single metric is usually **ΔGEX from OI change (net new/closed contracts), isolated from spot movement** — i.e., decompose the GEX change into:

**1. OI-driven change (the real signal)**
- Recompute GEX at *yesterday's* spot using *today's* OI, vs GEX at yesterday's spot using yesterday's OI.
- This isolates "did positioning actually shift" from "did GEX change because spot moved." This is the core metric — flow, not just level.

**2. Spot-driven change (the noise to strip out)**
- GEX today at today's spot vs GEX today at yesterday's spot, same OI.
- Since GEX is a nonlinear function of spot (peaks near ATM strikes), a lot of day-to-day GEX change is mechanical from price moving through the gamma curve, not from new positioning. If you don't separate this, you'll misread "GEX dropped" as bearish/bullish flow when it's just spot drifting away from a strike cluster.


| Metric | What it tells you |
|---|---|
| ΔOI by strike (calls vs puts separately) | Where new positioning is entering/exiting — the cleanest flow signal |
| ΔGEX (OI-isolated, as above) | Net effect of that flow in dollar-gamma terms |
| Volume vs OI ratio | Whether the day's volume is opening new positions or just churn/closing (high volume + flat OI = no net flow) |
| Shift in zero-gamma (flip) point | Whether the "regime" (long vs short gamma environment) is moving toward/away from spot — often the single most decision-relevant number for a swing trade |
| Change in peak positive/negative gamma strike | Whether the nearest wall of support/resistance is moving |

If you can only pick one number to watch daily: **the flip point's distance and direction relative to spot**, since it directly indicates whether you're moving into a stabilizing (long gamma) or volatile (short gamma) regime for the swing window — volume/OI changes are best used as the *diagnostic* for *why* the flip point moved, not the headline metric itself.