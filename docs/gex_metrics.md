## Standard Assumptions 

Using gamma in your options strategy focuses primarily on option market maker / dealers behavior in regards to hedging their own portfolio using the equity and futures markets.

Option Dealers are assumed to be delta-neutral or have no conviction about the direction of the market and are buying and selling options to profit from the bid/ask spread and fees only.

This means that price movement in any direction will affect the greeks and value of their portfolio and if they wish to remain hedged or delta neutral they will need to buy/sell equitites or futures to offset the affect of price movements.  They primarily do this using automated systems that constantly execute small orders to remain fully hedged.

A primary assumption is that the majority of the dealers portfolio is on the short side where they sell options to retail. It is a safe assumption what more than 50% of dealer positioning is selling options to retail investors.  It is possibly as high as 85% short positions.  


**Dealer sign convention**  
- Standard assumption: dealers long gamma from puts, short from calls (or the reverse convention some vendors use) — be explicit and consistent, and treat this as an assumption, not fact, since actual dealer positioning isn't public.  

# $ Gamma (notional gamma aka an aggregated dollar amount)  
  
**Dollar gamma, not raw gamma**  
- Convert to $ gamma exposure per 1% move (gamma × OI × 100 × spot² × 0.01) so contributions are comparable across strikes/expiries — raw gamma alone is meaningless for positioning analysis.  
  
##  Gamma Flip  
  
## Call Wall  
  
The options call wall is the single strike where net call gamma is highest for a given underlying.  
  
## Put Wall  
  
The Put Wall is the strike with the largest net put gamma for a given underlying.  
  
## HVL  
  
The HVL marks the geographic midpoint or heavy concentration center of total market maker exposure across the board. In many profiles, the HVL sits higher up in the strike range because open interest and absolute gamma tend to build heavily in the upper call structure.  
  
## Volatility (Vol) Trigger  

A level which characterisizes and divides prices action into lower / higher realized volatility.
  
The lowest qualifying call-side strike with meaningful positive GEX at or above the gamma flip.  
  
This marks the level where call dealer hedging (buy pressure) kicks in  meaningfully on the upside.  Often sits between Gamma Flip and Call Wall.  
  
A level at which realized volatility has historically accelerated. Implementations vary; the most common definition (used by GEXRadar) is the strike at which the cumulative negative-gamma below the G-Flip first exceeds a threshold — in plain English, the strike at which dealer hedging flips from "mildly negative" to "aggressively negative."

Trading use: a move _through_ the vol trigger from above is often the cleanest signal in the GEX toolkit that the day's character has changed. Position-sizing rules tightened above the vol trigger and loosened below it match the empirical realized-vol asymmetry.
# Hysteresis  
  
Hysteresis is the dependence of a system's state on its past history (path-dependence) in addition to its current state. How the system arrived at its current state influences the next step.

Applying this analogy to options/gex means that it matters if stock price declined to the current price or increased to reach it.  Depending on the direction of price before the current price determines what happens next.

The Hysteresis Effect: The actual mechanical pressure exerted on the market at a specific index level (e.g., S&P 500 at 6,000) depends heavily on the path the market took to get there. If the market drops sharply into a negative GEX pocket, dealers are forced into aggressive short-gamma selling. However, if the market rallies back up to that exact same 6,000 level, the dealer book's delta exposure, option decay (theta), and changing open interest mean the structural feedback loop reacts differently than it did on the way down.  
  
# Net Gex  
  
To compare one days net gex vs another will signal something about the relative x of that day vs others.  
Net Gex is less helpful for longer periods, but it probably makes sense to compare the monthly opex cycle to another  

## ATM Skew Slope  
The ATM skew slope (often referred to simply as the strike slope or skew slope around the money) measures the local steepness of the implied volatility (IV) curve right where the options are at-the-money.  
  
Instead of looking at the overall slope from deep OTM puts to deep Otm calls, it isolates how fast implied volatility changes per unit of strike or delta at the exact center of the options chain.  
  
## $R^2$  
  
## $\tau$ - Tau (Time to Expiration)  
  
Expressed in fraction of a year  
  
  
  
Sophisticated investors will weight GEX by DTE because weighting by DTE   
normalizes time, transforming GEX from a simple structural calculation into an accurate gauge of **real-world market-maker hedging pressure**.  
  
The Tau is used to weight which expirations contribute more to the gex calculation.  
Because gamma approaches large numbers as expiration approaches those near term expirations can have an outsized influence on a longer terms gex calculation.  
The Tau of 7 will artificially lower the influence of these options compared to later ones.  
  
Obviously for a longer term gex horizon of 90 days the tau can be larger to place more weight on the expirations further into the future  
  
  
## $\alpha$ - Alpha  
  
Alpha is the y-intercept of the volatility model or the volatility predicted even when historical volatility is zero.  
It can be interpreted as a sort of baseline volatility level  
---  

## Shift in $\Gamma$ flip 

This is very important metric for swing trading and it shows you if the gamma flip level is moving toward of away from the spot price
Whether the "regime" (long vs short gamma environment) is moving toward/away from spot — often the single most decision-relevant number for a swing trade

## Shift in $\Gamma$ Walls/VolTrigger

Understand how the put/call walls are moving relative to spot shows you where support/resistance is moving.

If you can only pick one number to watch daily: **the flip point's distance and direction relative to spot**, since it directly indicates whether you're moving into a stabilizing (long gamma) or volatile (short gamma) regime for the swing window — volume/OI changes are best used as the *diagnostic* for *why* the flip point moved, not the headline metric itself.


---  
**Practical ranking of what to track:**  
  
For day-over-day relative change tracking, the best single metric is usually **ΔGEX from OI change (net new/closed contracts), isolated from spot movement** — i.e., decompose the GEX change into:  
  
**1. OI-driven change (the real signal)**  
- Recompute GEX at *yesterday's* spot using *today's* OI, vs GEX at yesterday's spot using yesterday's OI.  
- This isolates "did positioning actually shift" from "did GEX change because spot moved." This is the core metric — flow, not just level.  
  
**2. Spot-driven change (the noise to strip out)**  
- GEX today at today's spot vs GEX today at yesterday's spot, same OI.  
- Since GEX is a nonlinear function of spot (peaks near ATM strikes), a lot of day-to-day GEX change is mechanical from price moving through the gamma curve, not from new positioning. If you don't separate this, you'll misread "GEX dropped" as bearish/bullish flow when it's just spot drifting away from a strike cluster.  
  
