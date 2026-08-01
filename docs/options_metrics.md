---  ## $\Delta$ Delta    
  
Delta represents the exposure an option has to the equity market or the degree to which the direction of price movement of the underlying will influence the options value.  
    
## $\Gamma$ - Gamma ( % $\Delta$ of Delta)    
Gamma is the $2^{nd}$ derivative of the options price *w.r.t* the price of the underlying or equivalently -- the derivative of *delta* or the rate of change in *delta*.  
  
Since *delta* represents the degree to which my options portfolio is exposed to the equity market (how sensitive or how much influence equity price movements have on my options values), gamma represents the degree to which that exposure/influence is increasing/decreasing.  
  
It is the convexity of the delta.    
    
A *gamma* of .05 means that if the underlying value rises by $1.00 than the delta increase by .05.  This is less intuitive and harder to work with than dollar *gamma*.    
    
  
  
    
---    
    
## Volatility Risk Premium    
    
A daily metric which calculates the daily historical volatility compared to the expected volatility based on IV.    
    
ATR greater than 1 std deviation compared to previous x days?    
    
Maybe this is a leading indicator about a reversal or breakout trend??    
    
## Churn  
  
The relationship between volume and OI signals the participants in the options market behavior.  It's preferable my most to keep volume in the numerator because the results are more intuitive with a larger number indicating higher "churn".  
  
We basically want to understan the 'net flow' and whether new positions are being established vs alot of 'noise' of daytrading  
  
$$\Huge\frac{\text{Volume}}{\text{Open Interest}}$$  
  
## $\Delta$ OI By Strike/Type  
  
A clean signal for flow to learn where new positioning is being established and where its diminishing  
  
## $\Gamma$ OI By Strike/Type  
  
The Net effect of the positioning flow above in $ terms.  This basically shows you the magnitude of positions in terms of dollars.  
  
  
  
## Metrics I want to explore  
  
  
  
## Put-Call Ratio  
  
The two numbers being close means put/call activity is spread similarly across strikes. 

When they diverge meaningfully, it tells you where along the strike range the imbalance sits — e.g. raw and notional both elevated means broad put-heavy positioning, but notional running much higher than raw specifically means the put OI is concentrated at higher-dollar strikes relative to where the calls sit (or vice versa if notional runs lower).  

Example for SPX:

Both metrics demonstrate more contracts and $ in puts than calls.  When weighting by strike we can see that in terms of dollar amount its a bit smaller relative difference than in terms of pure OI

Put-Call Raw           1.405
Put-Call Notional      1.258

Concretely: say calls have 1,000 contracts split evenly across a $700 strike and a $750 strike, and puts have 1,000 contracts entirely at a $700 strike.  
Notional = (1,000×700) / (500×700 + 500×750) = 700,000 / 725,000 ≈ 0.97 (puts are actually a slightly smaller dollar-weighted share, since some call OI sits at the higher strike)  
  
### Raw  (Pure OI)
  
Raw: total put open interest ÷ total call open interest — just counts contracts, treats a put at a \$100 strike the same as a put at a $1,000 strike.  
Raw = 1,000 / 1,000 = 1.0 (equal contract counts)  
  
### Notional  (weighted by $trike)
  
  
Notional: same ratio, but each side's OI is weighted by strike price first (OI × strike, summed) before dividing — so it approximates dollar exposure rather than contract count.  


  
  
  
# Historical Option Chain Data    
    
Where can I get historical option data?