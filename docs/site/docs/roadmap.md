---
title: Roadmap
---

<div class="dashboard">

<div class="dash-header">
<h1><span class="accent">→</span> ROADMAP</h1>
<div class="dash-meta"><span><span class="live-dot"></span>PHASE 8 ACTIVE</span></div>
</div>

<!-- ── Timeline ── -->
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
  <div class="step-sublabel">V2 Strategy</div>
</div>

</div>

<!-- ── Phase 0-6 ── -->
<div class="card glow-success">
<div style="display:flex;justify-content:space-between;align-items:center;">
<span class="badge badge--success">✓ COMPLETE</span>
</div>
<div style="margin-top:0.75rem;font-family:var(--fwd-font-mono);font-size:0.8rem;">
**Phase 0–6: Foundation** — Skeleton → Core → Observability → Boundaries → Operations → Test Strategy
</div>
</div>

<!-- ── Phase 7 ── -->
<div class="card glow-success" style="margin-top:0.75rem;">
<div style="display:flex;justify-content:space-between;align-items:center;">
<span class="badge badge--success">✓ COMPLETE</span>
</div>
<div style="margin-top:0.75rem;">
**Phase 7: Strategy Lab** — Gold Standard Found

| METRIC | UNFILTERED | ADX+EMA |
|--------|-----------|---------|
| Pass Rate | 12% | **75%** |
| Avg DD | 22.7% | **14.1%** |
| Max CL | 9.9 | **6.5** |

</div>
</div>

<!-- ── Phase 8 ── -->
<div class="card glow-accent" style="margin-top:0.75rem;">
<div style="display:flex;justify-content:space-between;align-items:center;">
<span class="badge badge--accent">● IN PROGRESS</span>
<span style="font-family:var(--fwd-font-mono);font-size:0.7rem;color:var(--fwd-text-dim);">DAY 2/14</span>
</div>
<div style="margin-top:0.75rem;">
**Phase 8: Paper Trading**

| COMPONENT | STATUS |
|-----------|--------|
| Executor V1 | ✓ 7 modules + 110 tests |
| Paper Engine | ● Running (REST polling) |
| Watchdog V2 | ● Hourly + circuit breaker |
| Housekeeping | ● Daily 09:00 Berlin |
| Monitor V1 | ○ Next |

**Phase 1 Criteria:**

| CRITERION | TARGET | CURRENT |
|-----------|--------|---------|
| Trades | ≥10 | 2 |
| Drawdown | ≤25% | 0.01% |
| Execution | ≥95% | — |
| Accounting | ✅ | ✅ |

<div class="progress-bar" style="margin-top:0.75rem;"><div class="progress-fill accent" style="width:14%"></div></div>
<div style="font-family:var(--fwd-font-mono);font-size:0.6rem;color:var(--fwd-text-dim);margin-top:0.25rem;">14% COMPLETE (2/14 DAYS)</div>
</div>
</div>

<!-- ── Phase 9 ── -->
<div class="card glow-neutral" style="margin-top:0.75rem;">
<div style="display:flex;justify-content:space-between;align-items:center;">
<span class="badge badge--neutral">○ NEXT</span>
</div>
<div style="margin-top:0.75rem;font-family:var(--fwd-font-mono);font-size:0.8rem;">
**Phase 9: Final Gate** — 14d testnet API: ≥5 orders, 0% API errors, kill-switch via API
</div>
</div>

<!-- ── Phase 10 ── -->
<div class="card glow-neutral" style="margin-top:0.75rem;">
<div style="display:flex;justify-content:space-between;align-items:center;">
<span class="badge badge--neutral">○ PLANNED</span>
</div>
<div style="margin-top:0.75rem;font-family:var(--fwd-font-mono);font-size:0.8rem;">
**Phase 10: V2 Strategy** — Regime-Score + Volatility-Parity + Sentiment Kill-Switch → [V2 Design](../v2-design/)
</div>
</div>

</div>