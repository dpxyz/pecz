---
title: Roadmap
---

# 🗺️ Roadmap

<div class="dashboard">

<div class="phase-timeline">

<div class="phase-step phase-step--done">
  <div class="step-dot"></div>
  <div class="step-label">0–6</div>
  <div class="step-sublabel">Foundation</div>
</div>

<div class="phase-step phase-step--done">
  <div class="step-dot"></div>
  <div class="step-label">7</div>
  <div class="step-sublabel">Strategy</div>
</div>

<div class="phase-step phase-step--active">
  <div class="step-dot"></div>
  <div class="step-label">8</div>
  <div class="step-sublabel">Paper Trading</div>
</div>

<div class="phase-step phase-step--pending">
  <div class="step-dot"></div>
  <div class="step-label">9</div>
  <div class="step-sublabel">Final Gate</div>
</div>

<div class="phase-step phase-step--pending">
  <div class="step-dot"></div>
  <div class="step-label">10</div>
  <div class="step-sublabel">V2</div>
</div>

</div>

<!-- ── Phase 0-6 ── -->
<div class="card" style="border-left: 4px solid var(--dash-success); padding: 1rem 1.25rem;">
**✅ Phase 0–6: Foundation** — Complete
Skeleton → Core → Observability → Boundaries → Operations → Test Strategy
</div>

<!-- ── Phase 7 ── -->
<div class="card" style="border-left: 4px solid var(--dash-success); padding: 1rem 1.25rem;">
**✅ Phase 7: Strategy Lab** — Gold Standard Found

| | Unfiltered | ADX+EMA Filter |
|---|---|---|
| Pass Rate | 12% | **75%** (CL≤12) |
| Avg DD | 22.7% | **14.1%** |
| Max CL | 9.9 | **6.5** |

→ [Baseline Strategy](strategy-lab/baseline/) · [Phase 7 Report](strategy-lab/PHASE7_ACCEPTANCE_REPORT/)
</div>

<!-- ── Phase 8 ── -->
<div class="card" style="border-left: 4px solid var(--dash-primary); padding: 1rem 1.25rem;">
**⭐ Phase 8: Paper Trading** — IN PROGRESS (Day 2/14)

| Component | Status |
|-----------|--------|
| Executor V1 (7 modules) | ✅ Built + 110 tests |
| Paper Engine | 🟢 Running (REST polling) |
| Watchdog V2 | 🟢 Hourly checks, circuit breaker |
| Housekeeping | 🟢 Daily 09:00, accounting checks |
| Discord Commands | ✅ !kill, !resume, !status, !watchdog-clear |
| Monitor V1 | ⬜ Next |

**Phase 1 Criteria (14 days):**

| Kriterium | Target | Current |
|-----------|--------|---------|
| Trades | ≥10 | 2 |
| Drawdown | ≤25% | 0.01% |
| Execution rate | ≥95% | — |
| Accounting invariant | ✅ | ✅ |
</div>

<!-- ── Phase 9 ── -->
<div class="card" style="border-left: 4px solid var(--dash-neutral); padding: 1rem 1.25rem;">
**⬜ Phase 9: Final Gate** — After Phase 1 passes

Phase 2 (14 days testnet API): ≥5 orders, 0% API errors, position visible, kill-switch via API
</div>

<!-- ── Phase 10 ── -->
<div class="card" style="border-left: 4px solid var(--dash-neutral); padding: 1rem 1.25rem;">
**⬜ Phase 10: V2 Strategy** — After validation complete

Regime-Score + Volatility-Parity + Sentiment Kill-Switch
→ [V2 Design Principles](v2-design/)
</div>

</div>