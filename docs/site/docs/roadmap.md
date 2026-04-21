---
title: Roadmap
---

<div class="dashboard">

<div class="dash-header">
<h1><span class="logo"><svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><polygon points="5,0.5 9.5,9.5 0.5,9.5"/></svg><svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><circle cx="5" cy="5" r="4.2"/></svg><svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><rect x="0.8" y="0.8" width="8.4" height="8.4"/></svg></span>PECZ<span class="accent">_</span>ROADMAP</h1>
<div class="dash-meta"><span><span class="live-dot"></span>PHASE 8</span></div>
</div>

<!-- ── Timeline ── -->
<div class="phase-timeline">

<div class="phase-step phase-step--done">
  <div class="step-dot"></div>
  <div class="step-label">0–6</div>
  <div class="step-sublabel">foundation</div>
</div>

<div class="phase-step phase-step--done">
  <div class="step-dot"></div>
  <div class="step-label">7</div>
  <div class="step-sublabel">strategy</div>
</div>

<div class="phase-step phase-step--active">
  <div class="step-dot"></div>
  <div class="step-label">8</div>
  <div class="step-sublabel">paper</div>
</div>

<div class="phase-step phase-step--pending">
  <div class="step-dot"></div>
  <div class="step-label">9</div>
  <div class="step-sublabel">gate</div>
</div>

<div class="phase-step phase-step--pending">
  <div class="step-dot"></div>
  <div class="step-label">10</div>
  <div class="step-sublabel">v2</div>
</div>

</div>

<!-- ── Phase 0-6 ── -->
<div class="card glow-success">
<div style="display:flex;justify-content:space-between;align-items:center;">
<span class="badge badge--success">✓ done</span>
</div>
<div style="margin-top:0.5rem;font-size:0.75rem;">
**Phase 0–6: Foundation** — skeleton → core → observability → boundaries → operations → test strategy
</div>
</div>

<!-- ── Phase 7 ── -->
<div class="card glow-success" style="margin-top:0.5rem;">
<div style="display:flex;justify-content:space-between;align-items:center;">
<span class="badge badge--success">✓ done</span>
</div>
<div style="margin-top:0.5rem;font-size:0.75rem;">
**Phase 7: Strategy Lab** — gold standard found

| metric | unfiltered | adx+ema |
|--------|-----------|---------|
| pass rate | 12% | **75%** |
| avg dd | 22.7% | **14.1%** |
| max cl | 9.9 | **6.5** |

</div>
</div>

<!-- ── Phase 8 ── -->
<div class="card glow-accent" style="margin-top:0.5rem;">
<div style="display:flex;justify-content:space-between;align-items:center;">
<span class="badge badge--accent">● active</span>
<span style="font-size:0.65rem;color:var(--fwd-text-dim);">DAY 2/14</span>
</div>
<div style="margin-top:0.5rem;font-size:0.75rem;">
**Phase 8: Paper Trading**

| component | status |
|-----------|--------|
| executor v1 | ✓ 7 modules + 110 tests |
| paper engine | ● running · rest polling |
| watchdog v2 | ● hourly · circuit breaker |
| housekeeping | ● daily 09:00 berlin |
| monitor v1 | ○ next |

**phase 1 criteria:**

| criterion | target | current |
|-----------|--------|---------|
| trades | ≥10 | 2 |
| drawdown | ≤25% | 0.01% |
| execution | ≥95% | — |
| accounting | ✅ | ✅ |

<div class="progress-bar" style="margin-top:0.5rem;"><div class="progress-fill accent" style="width:14%"></div></div>
<div style="font-size:0.6rem;color:var(--fwd-text-dim);margin-top:0.2rem;">14% complete (2/14 days)</div>
</div>
</div>

<!-- ── Phase 9 ── -->
<div class="card glow-neutral" style="margin-top:0.5rem;">
<div style="display:flex;justify-content:space-between;align-items:center;">
<span class="badge badge--neutral">○ next</span>
</div>
<div style="margin-top:0.5rem;font-size:0.75rem;">
**Phase 9: Final Gate** — 14d testnet api: ≥5 orders, 0% api errors, kill-switch via api

**pre-requisites (ADR-008):**
- [ ] heartbeat file (engine → 30s, watchdog → 60s)
- [ ] position recovery after restart
- [ ] external uptime monitor (UptimeRobot + Discord)
- [ ] escalation ladder implemented
- → [ADR-008: Crash & Uptime](../architecture/adr-008/)
</div>
</div>

<!-- ── Phase 10 ── -->
<div class="card glow-neutral" style="margin-top:0.5rem;">
<div style="display:flex;justify-content:space-between;align-items:center;">
<span class="badge badge--neutral">○ planned</span>
</div>
<div style="margin-top:0.5rem;font-size:0.75rem;">
**Phase 10: V2 Strategy** — regime-score + volatility-parity + sentiment kill-switch → [v2 design](../v2-design/)
</div>
</div>

</div>