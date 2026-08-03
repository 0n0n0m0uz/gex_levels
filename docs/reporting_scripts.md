## oi_churn.py (changes in conviction vs noise)

> when I see trading volume on an option today, how much of it is genuinely new bets, versus people just trading in and out of positions that already existed?

The 90 day report contains all expirations from 2 DTE through 90 DTE and therefore contains the 30 day report as a subset.

**Both the 90 and 30 day reports do not include 0DTE**


### --0DTE

The oi_churn.py reporting script in the --0DTE use case is only meaningful intraday.
For example, if you ran it 30 min after the open and again 1:30 min before the close you
could see how things have changed between the morning and afternoon.


## otm_call_flow.py

Provides a structural snapshot to show where call positioning is concentrated right now, near-term or far-term, and how much gamma pressure sits there

Shows us call flow at moderatley higher strikes, not lotto tickets which can signal if price is likely to rise into this resistance level

> is real money building a bullish bet that could act as resistance on the way up, and is that pressure growing or fading?

So in short: it's a "how much real dollar-weighted buying pressure is building toward becoming resistance, and is it accelerating" gauge — same conceptual family as oi_churn.py's conviction-vs-noise question, but here the question is specifically about directional call-buying pressure rather than open-interest churn.

Where OTM call positioning sits, structurally — the Near/Far split and the 67%-style share ratio are the one part that's meaningful without any history. It answers "is call positioning concentrated in the next 3 weeks (reactive, closer to expiry) or spread further out (structural)?" — that's a real, standalone read.