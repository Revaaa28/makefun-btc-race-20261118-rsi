"""Rev's RSI bot for the make.fun cbBTC bars-replay race
(agent-fun/bars-replay/v1) — the owner's own strategy, implemented
as he specified it:

  * Entry: Wilder RSI(14) on 1-minute closes in the oversold zone —
    buy when RSI has been under 30 and crosses back up through 30
    (the maximising variant he invited: same oversold zone, but the
    entry waits for the fall to stop instead of catching it
    mid-flight; measured below against the pure form).
  * Exit (his rule): at the entry bar, record the standing high —
    the highest high printed from the window's start up to and
    including the entry bar, the ATH as it stood when the bot
    entered. The first later bar whose high exceeds that reference
    arms the exit, and the bot sells 1 bar after that print.
  * Backstops (additions he invited, firing only when his exit has
    not): a -70 bps hard stop from the actual buy fill price, and a
    420-bar time stop. After any exit, a 5-bar cooldown, then the
    bot re-arms for the next oversold event — an all-day loop.
    Entries are all-in.

Measured on the kit's dev window (24h ending 2026-11-18T14:44Z, a
-2.80% downtrend; buy and hold scores -31.633698 USDC after costs)
with a fill-faithful simulator (the harness's own fill math, integer
for integer; it reproduces that buy-and-hold score exactly):

  * Shipped form (cross-up entry): net PnL -23.800 USDC over 6 round
    trips, win rate 33%, profit factor 0.37, expectancy -$3.97 per
    trade, max drawdown 2.92% of the starting cash. Half windows:
    first half -10.75, second half -17.30. THIS FAILS THE DEV GATE:
    the entry does not race unless the server's dev grade is above
    zero, and no faithful variant measured above zero.
  * Pure form (buy while RSI < 30): -32.940 USDC, 8 round trips —
    worse; it buys deeper into falls that keep falling.
  * His exit fired ZERO times at the shipped backstops: in this
    falling tape, price never reclaimed the entry-time standing
    high before a backstop closed the trade. Every exit was a
    backstop (4 stops at about -$9.3 each — a -70 bps close trigger
    realises about -93 bps after the exit fill's own costs — and 2
    time stops, which were the only winners, +11.06 and +3.13: the
    trades that survived 420 bars caught the relief drift).
  * The rule itself works when the tape cooperates: with a 900-bar
    time stop, the trade entered at bar 72 was held until bar 508
    printed above its entry-time high (65,190 over 65,118) and the
    ATH exit sold it 1 bar later for +18.34 — that variant still
    nets -10.80 overall. A grid over stop {50,70,100,150} x time
    {240,420,600,900} for both entry forms: every cell negative
    (best -10.80). Entering on the cross-up out of a deeper zone
    (RSI 25) measured -9.05 — the least-bad sensitivity, still
    negative; the shipped threshold stays at his 30.
  * The trailing-240-bar reference high in place of the standing
    high changed no exit on this window (identical PnL): after
    mid-window both references sit far above a falling tape.

The honest summary: on a day that only falls, "buy oversold, sell
when price makes a new high versus when you entered" has no new
high to sell into, so the backstops do all the exiting and the
round-trip cost (~26 bps) plus the drift beat it. The design is
shipped exactly as specified so the numbers above are his
strategy's, not a substitute's.

Deterministic: no wall clock, no randomness, no environment reads;
the only inputs are the hello and the batches. All arithmetic is
integer, identical every run.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars  # noqa: E402

SYMBOL = "CBBTC"

PARAMS = {
    "rsi_period": 14,       # Wilder RSI period (Rev: RSI(14))
    "rsi_entry": 30,        # oversold threshold (Rev: below 30)
    "entry_mode": "crossup",  # buy when RSI crosses back up through 30
    "stop_bps": 70,         # backstop: hard stop below the fill price
    "time_stop": 420,       # backstop: max bars held
    "cooldown": 5,          # bars after an exit before re-entry
    "size_pct": 100,
    "buy_slip_bps": 10000,
    "sell_slip_bps": 10000,
}


class Bot:
    def __init__(self, hello):
        self.p = dict(PARAMS)
        self.min_notional = int(hello["fees"]["min_notional_quote_units"])
        self.closes = []
        self.highs = []
        self.avg_gain = 0       # Wilder RSI state, scaled by 10**6
        self.avg_loss = 0
        self.rsi_bars = 0
        self.prev_rsi = None
        self.running_high = 0   # highest high since the window start
        self.ref_high = 0       # standing high recorded at the entry
        self.entry_fill_price = 0
        self.entry_fill_bar = -1
        self.ath_armed = False  # a bar printed above ref_high
        self.last_exit = -10 ** 9
        self.pending = None
        self.order_n = 0

    def _next_id(self, tag):
        self.order_n += 1
        return "%s%d" % (tag, self.order_n)

    def _update_rsi(self, close, prev_close):
        if prev_close is None:
            return
        chg = close - prev_close
        gain = chg if chg > 0 else 0
        loss = -chg if chg < 0 else 0
        n = self.p["rsi_period"]
        if self.rsi_bars < n:
            self.avg_gain += gain * 10 ** 6 // n
            self.avg_loss += loss * 10 ** 6 // n
        else:
            self.avg_gain = (self.avg_gain * (n - 1) + gain * 10 ** 6) // n
            self.avg_loss = (self.avg_loss * (n - 1) + loss * 10 ** 6) // n
        self.rsi_bars += 1

    def _rsi(self):
        total = self.avg_gain + self.avg_loss
        if total == 0 or self.rsi_bars < self.p["rsi_period"]:
            return 100
        return 100 * self.avg_gain // total

    def on_batch(self, state, batch):
        prev_close = self.closes[-1] if self.closes else None
        for bar in batch["bars"]:
            if bar["symbol"] == SYMBOL:
                self.closes.append(int(bar["c"]))
                self.highs.append(int(bar["h"]))
        if not self.closes:
            return None
        i = len(self.closes) - 1
        close = self.closes[-1]
        if self.highs[-1] > self.running_high:
            self.running_high = self.highs[-1]
        for fill in batch["fills"]:
            if self.pending == "buy" and fill["side"] == "buy":
                self.pending = None
                self.entry_fill_price = int(fill["price"])
                self.entry_fill_bar = i
            elif self.pending == "sell" and fill["side"] == "sell":
                self.pending = None
        self._update_rsi(close, prev_close)
        rsi = self._rsi()
        p = self.p
        if state.warming_up:
            self.prev_rsi = rsi
            return None
        holding = state.positions.get(SYMBOL)

        if holding is not None and self.pending is None:
            exit_now = False
            if self.ath_armed:
                exit_now = True               # his exit: +1 bar
            elif (self.entry_fill_price > 0
                  and (close - self.entry_fill_price) * 10000
                  // self.entry_fill_price <= -p["stop_bps"]):
                exit_now = True               # backstop: hard stop
            elif (self.entry_fill_bar >= 0
                  and i - self.entry_fill_bar >= p["time_stop"]):
                exit_now = True               # backstop: time stop
            if exit_now:
                self.pending = "sell"
                self.last_exit = i
                self.ath_armed = False
                self.prev_rsi = rsi
                return [{
                    "side": "sell",
                    "client_id": self._next_id("s"),
                    "symbol": SYMBOL,
                    "qty": holding.qty,
                    "max_slippage_bps": p["sell_slip_bps"],
                }]
            # No exit decided: watch for the new-high print (his rule).
            if self.highs[-1] > self.ref_high:
                self.ath_armed = True
            self.prev_rsi = rsi
            return None

        if holding is not None or self.pending is not None:
            self.prev_rsi = rsi
            return None
        if i - self.last_exit < p["cooldown"]:
            self.prev_rsi = rsi
            return None
        if self.rsi_bars < p["rsi_period"]:
            self.prev_rsi = rsi
            return None

        signal = (self.prev_rsi is not None
                  and self.prev_rsi < p["rsi_entry"] <= rsi)
        if not signal:
            self.prev_rsi = rsi
            return None

        notional = state.cash * p["size_pct"] // 100
        room = state.weight_room(SYMBOL)
        if room < notional:
            notional = room
        if notional < self.min_notional:
            self.prev_rsi = rsi
            return None
        self.pending = "buy"
        self.ref_high = self.running_high
        self.ath_armed = False
        self.entry_fill_price = 0
        self.entry_fill_bar = -1
        self.prev_rsi = rsi
        return [{
            "side": "buy",
            "client_id": self._next_id("b"),
            "symbol": SYMBOL,
            "notional_quote_units": notional,
            "max_slippage_bps": p["buy_slip_bps"],
        }]


def main():
    holder = {}

    def on_batch(state, batch):
        bot = holder.get("bot")
        if bot is None:
            bot = holder["bot"] = Bot(state.hello)
        return bot.on_batch(state, batch)

    makefun_bars.run(on_batch)


if __name__ == "__main__":
    main()
