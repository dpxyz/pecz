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
    <span style="font-weight:600;color:var(--fwd-text-bright);">Phase 0–6: Foundation</span>
    <span class="badge badge--success">✓ done</span>
  </div>
  <div style="margin-top:0.3rem;font-size:0.75rem;color:var(--fwd-text-muted);">
    skeleton → core → observability → boundaries → operations → test strategy
  </div>
</div>

<!-- ── Phase 7 ── -->
<div class="card glow-success" style="margin-top:0.5rem;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="font-weight:600;color:var(--fwd-text-bright);">Phase 7: Strategy Lab</span>
    <span class="badge badge--success">✓ done</span>
  </div>
  <div style="margin-top:0.3rem;font-size:0.75rem;color:var(--fwd-text-muted);">Gold standard found: ADX+EMA</div>
  <div class="grid-3" style="gap:0.3rem;margin-top:0.4rem;">
    <div class="card" style="padding:0.3rem 0.5rem;text-align:center;">
      <div style="font-size:0.6rem;color:var(--fwd-text-muted);">pass rate</div>
      <div style="font-size:0.85rem;font-weight:600;color:var(--fwd-accent);">75%</div>
      <div style="font-size:0.55rem;color:var(--fwd-text-dim);">vs 12% unfiltered</div>
    </div>
    <div class="card" style="padding:0.3rem 0.5rem;text-align:center;">
      <div style="font-size:0.6rem;color:var(--fwd-text-muted);">avg dd</div>
      <div style="font-size:0.85rem;font-weight:600;color:var(--fwd-accent);">14.1%</div>
      <div style="font-size:0.55rem;color:var(--fwd-text-dim);">vs 22.7% unfiltered</div>
    </div>
    <div class="card" style="padding:0.3rem 0.5rem;text-align:center;">
      <div style="font-size:0.6rem;color:var(--fwd-text-muted);">max cl</div>
      <div style="font-size:0.85rem;font-weight:600;color:var(--fwd-accent);">6.5</div>
      <div style="font-size:0.55rem;color:var(--fwd-text-dim);">vs 9.9 unfiltered</div>
    </div>
  </div>
</div>

<!-- ── Phase 8 ── -->
<div class="card glow-accent" style="margin-top:0.5rem;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="font-weight:600;color:var(--fwd-text-bright);">Phase 8: Paper Trading</span>
    <div style="display:flex;align-items:center;gap:0.5rem;">
      <span class="badge badge--accent">● active</span>
      <span id="roadmap-day" style="font-size:0.65rem;color:var(--fwd-text-dim);">—</span>
    </div>
  </div>

  <div style="margin-top:0.4rem;" class="section-label">components</div>
  <div class="grid-2" style="gap:0.3rem;">
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">executor v1</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">✓ 7 modules + 297 tests</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">paper engine</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">● running · rest</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">watchdog v2</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">● hourly · breaker</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">housekeeping</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">● daily 09:00</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">monitor v1</span>
      <span style="font-size:0.65rem;color:var(--fwd-accent);">● live</span>
    </div>
  </div>

  <div style="margin-top:0.4rem;" class="section-label">foundry v7</div>
  <div class="grid-2" style="gap:0.3rem;">
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">V32 (5w)</span>
      <span style="font-size:0.65rem;color:var(--fwd-accent);">WF 88.3 · IS 1.28</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">V32 (10w)</span>
      <span style="font-size:0.65rem;color:var(--fwd-danger);">WF 23.3 · FAIL</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">search</span>
      <span style="font-size:0.65rem;color:var(--fwd-text-muted);">150+ · 0 10w-passed</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">mode</span>
      <span style="font-size:0.65rem;color:var(--fwd-accent);">adaptive · 10w std</span>
    </div>
  </div>

  <div style="margin-top:0.4rem;" class="section-label">phase 1 criteria</div>
  <div class="grid-2" style="gap:0.3rem;">
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">trades</span>
      <span style="font-size:0.65rem;color:var(--fwd-accent);">≥10 · 2 done</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">drawdown</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">≤25% · 0.51%</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">execution</span>
      <span style="font-size:0.65rem;color:var(--fwd-text-muted);">≥95% · —</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">accounting</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">✅ · ✅</span>
    </div>
  </div>

  <div class="progress-bar" style="margin-top:0.5rem;"><div class="progress-fill accent" style="width:21%"></div></div>
  <div style="font-size:0.6rem;color:var(--fwd-text-dim);margin-top:0.2rem;">21% complete (3/14 days)</div>
</div>

<!-- ── Phase 9 ── -->
<div class="card glow-neutral" style="margin-top:0.5rem;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="font-weight:600;color:var(--fwd-text-bright);">Phase 9: Final Gate</span>
    <span class="badge badge--neutral">○ next</span>
  </div>
  <div style="margin-top:0.3rem;font-size:0.75rem;color:var(--fwd-text-muted);">14d testnet api: ≥5 orders, 0% api errors, kill-switch via api</div>
  <div style="margin-top:0.3rem;font-size:0.7rem;color:var(--fwd-text-dim);">pre-reqs (ADR-008):</div>
  <div style="margin-top:0.2rem;" class="grid-2" style="gap:0.2rem;">
    <div style="font-size:0.68rem;color:var(--fwd-text-muted);">☐ heartbeat file</div>
    <div style="font-size:0.68rem;color:var(--fwd-text-muted);">☐ position recovery</div>
    <div style="font-size:0.68rem;color:var(--fwd-text-muted);">☐ uptime monitor</div>
    <div style="font-size:0.68rem;color:var(--fwd-text-muted);">☐ escalation ladder</div>
  </div>
  <div style="margin-top:0.2rem;font-size:0.68rem;">→ <a href="../architecture/adr-008/" style="color:var(--fwd-accent);">ADR-008: Crash & Uptime</a></div>
</div>

<!-- ── Phase 10 ── -->
<div class="card glow-neutral" style="margin-top:0.5rem;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="font-weight:600;color:var(--fwd-text-bright);">Phase 10: V2 Strategy</span>
    <span class="badge badge--neutral">○ planned</span>
  </div>
  <div style="margin-top:0.3rem;font-size:0.75rem;color:var(--fwd-text-muted);">regime-score + volatility-parity + sentiment kill-switch</div>
  <div style="margin-top:0.2rem;font-size:0.68rem;">→ <a href="../v2-design/" style="color:var(--fwd-accent);">V2 Design</a></div>
</div>

</div>

<script>
(function() {
  const start = new Date('2026-04-20T00:00:00+02:00');
  const day = Math.floor((Date.now() - start) / 86400000) + 1;
  const el = document.getElementById('roadmap-day');
  if (el) el.textContent = 'DAY ' + Math.max(day,1) + '/14';
})();
</script>