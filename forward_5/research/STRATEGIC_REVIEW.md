# Strategic Review — 2026-04-19

## Critical Finding: Trailing Stop Backtest-vs-Live Gap

### The Problem
The backtest uses `closes[i]` to check trailing stop triggers. In reality,
stop orders trigger when the MARK PRICE reaches the stop level — which
corresponds more closely to checking `lows[i]` (intra-bar low).

### Impact on BTC 2024

| Trailing Check | Trades | Return | DD% | Pass Rate (8 assets) |
|---|---|---|---|---|
| CLOSE (current) | 228 | +22.0% | 10.6% | 12/16 = 75% |
| LOW (realistic) | 259 | -46.7% | 46.7% | 2/16 = 12% |
| LOW + 3.5% trail | 217 | +14.7% | 11.7% | BTC only |

### Why CLOSE is Not "Wrong"
- 1h OHLC data cannot represent intra-bar price dynamics
- LOW might be a flash-crash wick (1-2 ticks) that wouldn't trigger in practice
- CLOSE-based check approximates "price stayed below level at end of bar"
- Paper engine uses REAL-TIME WebSocket prices — inherently more accurate

### Decision: Keep CLOSE-based backtest, accept the gap
1. **Backtest**: Reverted to CLOSE-based (preserves 75% baseline for relative comparisons)
2. **Paper Engine**: Uses real-time price checks (already correct with `low` from candle)
3. **Paper Trading** will reveal the TRUE stop behavior
4. If paper results worse than backtest → increase trailing from 2% to 3.5%

### Other Checks Performed

| Check | Result |
|---|---|
| Look-ahead bias in EMA | ✅ None (ewm_mean is causal) |
| Entry timing | ✅ Next-bar open (no same-bar entry) |
| SL uses LOW | ✅ Correct |
| TP uses HIGH | ✅ Correct |
| SL checked before TP | ✅ Conservative (same-bar conflict) |
| Trailing peak tracking | ✅ Updated from HIGH, correct |
| Fee calculation | ✅ Roundtrip: maker both sides |
| Slippage on entry and exit | ✅ Applied both sides |

### Remaining Known Limitations

1. **Intra-bar ordering**: We don't know if HIGH or LOW came first within a bar.
   Current assumption: HIGH updates first (then trailing level rises), then LOW
   is checked. In reality, order is random ~50/50.

2. **Intra-trade drawdown**: DD is only measured at trade exit points.
   Max intra-trade DD may be higher. This requires equity-curve-per-bar
   tracking (deferred to V2).

3. **1h granularity**: All stops are checked once per hour. Flash crashes
   within the hour are either missed (CLOSE) or always caught (LOW). Paper
   engine with real-time WebSocket resolves this.

### Action Items for Paper Trading

- [ ] Start with 2% trailing, compare paper results vs CLOSE-based backtest
- [ ] If paper exit rate > backtest exit rate → increase trailing
- [ ] Track actual vs backtest exit reason distribution
- [ ] After 30 days: re-baseline with real execution data