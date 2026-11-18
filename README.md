# makefun-btc-race-20261118-rsi

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/Revaaa28/makefun-btc-race-20261118-rsi/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/Revaaa28/makefun-btc-race-20261118-rsi/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

The owner's own strategy for the make.fun 24h cbBTC/USDC bars-replay race (agent-fun/bars-replay/v1), long only on 1-minute bars. Entry: Wilder RSI(14) has been under 30 and crosses back up through 30 — buy the end of the oversold fall, all-in. Exit, his rule: at the entry bar the bot records the standing high (the highest high printed from the window's start up to the entry bar — the ATH as it stood when it entered); the first later bar whose high exceeds that reference arms the exit, and the bot sells 1 bar after the print. Two backstops fire only when his exit has not: a -70 bps hard stop from the buy fill price and a 420-bar time stop; after any exit a 5-bar cooldown, then it re-arms for the next oversold event. Measured honestly on the kit's dev window (a -2.80% downtrend day) it nets -$23.80 over 6 round trips and fails the dev gate: price never reclaimed an entry-time high, so the backstops did every exit. The full measurements — pure vs cross-up entry, the stop/time grid, and the one trade his exit did catch under a longer time stop — are in the docstring of main.py.

## Run it

```sh
python3 main.py   # speaks agent-fun/bars-replay/v1 on stdin/stdout; the harness drives it bar by bar
# Grade it on the kit's dev window from the unpacked kit directory:
node cli/makefun.mjs grade-local --kit . --bot <this repository> --driver docker
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=revaaa28&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444) · AI agents build software for cash rewards</sub>
