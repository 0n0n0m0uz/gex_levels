## oi_churn.py (changes in conviction vs noise)

> when I see trading volume on an option today, how much of it is genuinely new bets, versus people just trading in and out of positions that already existed?

The 90 day report contains all expirations from 2 DTE through 90 DTE and therefore contains the 30 day report as a subset.

**Both the 90 and 30 day reports do not include 0DTE**


### --0DTE

The oi_churn.py reporting script in the --0DTE use case is only meaningful intraday.
For example, if you ran it 30 min after the open and again 1:30 min before the close you
could see how things have changed between the morning and afternoon.
