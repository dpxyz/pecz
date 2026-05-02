# Foundry V12 — Context-Aware LLM Strategy Discovery

## Philosophy
LLM finds strategies we wouldn't think of — but needs our proven context.
Not random mutation. Not manual grid search. **Informed creativity.**

## What Changed vs V10/V11
- V10: LLM had no context → repetitive, 0/60 WF-passed
- V11: Manual with context → better, but limited by our imagination
- V12: LLM WITH full context → creative combinations of proven building blocks

## Building Blocks (Proven Edge)
These are the ONLY allowed components. LLM must combine them, not invent new ones.

### Signal Types (PROVEN)
1. **Bear Funding MR**: z<-1 (BTC+ETH), z<-1.5 (SOL) → Long
2. **Bull Pullback**: z between -1.0 and -0.3 in bull → Long (HYP-06)
3. **BTC FGI Filter**: FGI<40 confirms bear signal (WF 6/6)
4. **ETH Volume Confirm**: vol_ratio > 1.5σ confirms signal (WR 54→68%)

### Timeframes (PROVEN)
1. **1h**: Standard, all assets
2. **4h**: BTC ONLY (5x PnL improvement, HYP-02)

### Regime (PROVEN)
1. **bull200**: close > EMA200 → bull
2. **bull50**: close > EMA50 → strong trend

### Filters (MIXED)
1. **FGI**: Fear/Greed Index — works for BTC bear, inconclusive elsewhere
2. **DXY**: FAILED — do NOT use (HYP-04, all assets FAIL)
3. **Volume spike**: Works for ETH only, hurts BTC/SOL
4. **OI**: Not available in historical data

### Exit Types (PROVEN)
1. **Time-based 24h**: Primary exit (funding decays)
2. **Emergency SL 4%**: Black swan only
3. **Trailing**: DISABLED (kills recovering trades)

## Constraints
- **NO** DXY in any strategy (proven FAIL)
- **NO** momentum/breakout entries (proven FAIL)
- **NO** short signals (proven FAIL, HYP-01)
- **NO** threshold sweeping (one threshold per signal type)
- **NO** new indicators not in building blocks
- **STRICT** `<` threshold: z=-1.0 does NOT trigger z<-1.0
- WF Gate: ≥4/6 OOS profitable, cum PnL > 0, ≥30 trades

## LLM Context Injection
Each prompt includes:
1. All HYP-01 through HYP-06 results (what worked, what failed)
2. Top 10 strategies by WF robustness
3. Current V2 signal set (baseline to beat)
4. Building blocks and constraints
5. Previous iteration results (feedback loop)

## LLM Task
"Given these building blocks and proven results, create 10 novel strategy COMBINATIONS we haven't tested. Focus on:
- Regime-adaptive signals (different rules for bull vs bear)
- Multi-timeframe combinations (1h + 4h for BTC)
- Cross-asset patterns (ETH volume confirm with funding)
- Exit condition variants (partial profit at 12h?)
- Cooldown variants (24h vs funding-cycle aligned)"

## Architecture
1. **Iteration 1**: LLM generates 10 strategies from context
2. **Backtest all 10** on all 3 assets × 2 timeframes
3. **WF Gate filter** (≥4/6 OOS, cum > 0, ≥30 trades)
4. **Feedback**: Pass/fail results fed back to LLM
5. **Iteration 2**: LLM refines based on feedback, generates 10 more
6. **Iteration 3**: Final refinement
7. **Result**: Top strategies by composite fitness

## Assets
- BTCUSDT, ETHUSDT, SOLUSDT (1h + 4h for BTC)

## Expected Output
- `research/foundry_v12_results.json`
- Top strategies ranked by composite fitness
- Comparison vs V2 baseline