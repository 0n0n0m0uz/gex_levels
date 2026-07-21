# 0DTE Calculation Overview

Calculating Gamma Exposure (GEX) for zero-day-to-expiration (0DTE) options differs significantly from longer-dated options due to the extreme compression of time, unique order flow dynamics, and mathematical instability of the black-scholes formula

## Black-Scholes Gamma Calculation Issues w 0DTE

Because the Time to Expiration of 0DTE options when converted to the standard fraction of a year is so small and in the denominator
Spot on. The square root of time (\sqrt{T}) gets smaller and smaller as expiration approaches, and because it sits in the denominator, the overall gamma gets larger and larger.
As T approaches zero, dividing by a progressively smaller fraction acts like a multiplier, driving the gamma value straight up toward infinity.

Black scholes wont work under 15 min to expiration because denom shrinks faster than numerator and gamma becomes infinite and you get eoors so otherfunctions are used or just stop 

To calculate time to expiration (T) for a 0DTE option in fractional years, you divide the remaining seconds (or minutes) by the total number of seconds in a standard trading year. Better use a 252 day year compare to 365

## Inverse square root relation

1. Get Spot Price of underlying stock
2. Download the Options Chain for the underlying stock
3. Filter for expirations expiring today or DTE of 1 or less than 1 and discard the rest
4. Filter away Oi < 1, Vol < 1, ask - bid > threshold, bid of 0 (no buyer)
5. Filter away ITM and OTM options beyond threshold, IV outliers, bid ask/crossew, bad timestamps
6. Scaling 0dte to prevent issues with bs formula denomination explosion
7. Calculate gmma of each contract using bs formula
8. Multiply each contracts gamma by the contracts oi which scales up the gamma to represent the total hedginmg prressuree on for all those contrcts on the dealers boojs
9 gamma x oi x 100 x spot squared x .01 gives you dollar notional or the dollar amount dealers need hedge for a 1% move.  This lets you compare different priced stocks and their effect on hedging oressure