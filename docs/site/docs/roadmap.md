---
title: Roadmap
---

<div class="dashboard">

<div class="dash-header">
<h1><span class="logo"><svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><polygon points="5,0.5 9.5,9.5 0.5,9.5"/></svg><svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><circle cx="5" cy="5" r="4.2"/></svg><svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><rect x="0.8" y="0.8" width="8.4" height="8.4"/></svg></span>PECZ<span class="accent">_</span>ROADMAP</h1>
<div class="dash-meta"><span><span class="live-dot"></span>G2→G3 — 90 DAY TRACK RECORD</span></div>
</div>

<!-- ── Timeline ── -->
<div class="phase-timeline">

<div class="phase-step phase-step--done">
  <div class="step-dot"></div>
  <div class="step-label">0</div>
  <div class="step-sublabel">foundation</div>
</div>

<div class="phase-step phase-step--done">
  <div class="step-dot"></div>
  <div class="step-label">1</div>
  <div class="step-sublabel">discovery</div>
</div>

<div class="phase-step phase-step--active">
  <div class="step-dot"></div>
  <div class="step-label">2</div>
  <div class="step-sublabel">validation</div>
</div>

<div class="phase-step phase-step--pending">
  <div class="step-dot"></div>
  <div class="step-label">3</div>
  <div class="step-sublabel">operations</div>
</div>

</div>

<!-- ── Phase 0: Foundation ── -->
<div class="card glow-accent">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="font-weight:600;color:var(--fwd-text-bright);">Phase 0: Foundation</span>
    <div style="display:flex;align-items:center;gap:0.5rem;">
      <span class="badge badge--success">✓ complete</span>
      <span style="font-size:0.65rem;color:var(--fwd-text-dim);">W1-4</span>
    </div>
  </div>

  <div style="margin-top:0.4rem;" class="section-label">0.1 V2 Engine Fix</div>
  <div class="grid-2" style="gap:0.3rem;">
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">SOL z∈[-0.5,0)</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">✓ V13b champion</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">Trailing Stop</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">✓ disabled</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">SL 4%</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">✓ Prop-Firm compat</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">Tests</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">✓ 464/467 green</span>
    </div>
  </div>

  <div style="margin-top:0.4rem;" class="section-label">0.2 Statistical Robustness</div>
  <div class="grid-2" style="gap:0.3rem;">
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">DSR + Monte Carlo</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">✓ 1000 resamples</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">Bonferroni + BH-FDR</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">✓ FDR control</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">CPCV Validation</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">✓ combinatorial</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">Edge Registry ρ&lt;0.4</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">✓ 7 entries</span>
    </div>
  </div>

  <div class="progress-bar" style="margin-top:0.5rem;"><div class="progress-fill accent" style="width:100%"></div></div>
  <div style="font-size:0.6rem;color:var(--fwd-text-dim);margin-top:0.2rem;">100% complete</div>
</div>

<!-- ── Phase 1: Signal Discovery ── -->
<div class="card glow-accent" style="margin-top:0.5rem;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="font-weight:600;color:var(--fwd-text-bright);">Phase 1: Signal Discovery</span>
    <div style="display:flex;align-items:center;gap:0.5rem;">
      <span class="badge badge--success">✓ complete</span>
      <span style="font-size:0.65rem;color:var(--fwd-text-dim);">W5-8</span>
    </div>
  </div>

  <div style="margin-top:0.4rem;" class="section-label">5 Validated Signals (CPCV, 2yr data)</div>
  <div class="grid-2" style="gap:0.3rem;">
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">BTC mild_neg + bull200</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">PBO 0.13 ✅</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">ETH mild_neg + bull200</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">PBO 0.13 ✅</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">BTC crosssec z&lt;-1 + bull200</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">PBO 0.20 ✅</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">OI Surge SOL h48 + bull200</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">PBO 0.33 ✅</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">LS Ratio SOL &gt;5 Short</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">PBO 0.33 ✅</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">DXY Confluence Filter</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">ρ=-0.72 ✅</span>
    </div>
  </div>

  <div style="margin-top:0.4rem;" class="section-label">Correlation Check (ρ &lt; 0.4 = uncorrelated)</div>
  <div class="grid-2" style="gap:0.3rem;">
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">BTC vs ETH mild_neg</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">ρ = 0.17 ✅</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">LS Ratio vs Funding</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">ρ = -0.04 ✅</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">Crosssec vs BTC fund</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">ρ = 0.02 ✅</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">OI Surge vs LS Ratio</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">ρ = 0.28 ✅</span>
    </div>
  </div>

  <div class="progress-bar" style="margin-top:0.5rem;"><div class="progress-fill accent" style="width:100%"></div></div>
  <div style="font-size:0.6rem;color:var(--fwd-text-dim);margin-top:0.2rem;">100% complete — 5 uncorrelated signals validated</div>
</div>

<!-- ── Phase 2: Validation & Scaling ── -->
<div class="card glow-neutral" style="margin-top:0.5rem;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="font-weight:600;color:var(--fwd-text-bright);">Phase 2: Validation & Scaling</span>
    <div style="display:flex;align-items:center;gap:0.5rem;">
      <span class="badge badge--accent">● active</span>
      <span style="font-size:0.65rem;color:var(--fwd-text-dim);">W9-24</span>
    </div>
  </div>
  <div style="margin-top:0.3rem;font-size:0.75rem;color:var(--fwd-text-muted);">90-day paper track record · Prop-Firm evaluation · Gewerbeanmeldung</div>
  <div class="grid-2" style="gap:0.3rem;margin-top:0.4rem;">
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">V2 Engine (5 signals)</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">✓ live</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">DXY + FGI Filters</span>
      <span style="font-size:0.65rem;color:var(--fwd-success);">✓ confluence</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">90d Paper Track Record</span>
      <span style="font-size:0.65rem;color:var(--fwd-accent);">⟳ Day 1</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">Breakout Prop</span>
      <span style="font-size:0.65rem;color:var(--fwd-text-muted);">$25k · 6% MaxDD</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">§15 EStG</span>
      <span style="font-size:0.65rem;color:var(--fwd-text-muted);">Gewerbe · kein Deckel</span>
    </div>
    <div class="card" style="padding:0.25rem 0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:0.72rem;color:var(--fwd-text);">Copy Trading</span>
      <span style="font-size:0.65rem;color:var(--fwd-text-muted);">nach 90d · Bitget</span>
    </div>
  </div>
  <div class="progress-bar" style="margin-top:0.5rem;"><div class="progress-fill accent" style="width:10%"></div></div>
  <div style="font-size:0.6rem;color:var(--fwd-text-dim);margin-top:0.2rem;">~10% complete (engine live, track record started)</div>
</div>

<!-- ── Phase 3: Operations ── -->
<div class="card glow-neutral" style="margin-top:0.5rem;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="font-weight:600;color:var(--fwd-text-bright);">Phase 3: Operational Excellence</span>
    <div style="display:flex;align-items:center;gap:0.5rem;">
      <span class="badge badge--neutral">○ planned</span>
      <span style="font-size:0.65rem;color:var(--fwd-text-dim);">W25-52</span>
    </div>
  </div>
  <div style="margin-top:0.3rem;font-size:0.75rem;color:var(--fwd-text-muted);">Multi-venue · Edge decay monitoring · Portfolio risk · Scaling</div>
</div>

<!-- ── Gates ── -->
<div class="card glow-accent" style="margin-top:0.5rem;">
  <div style="font-weight:600;color:var(--fwd-text-bright);">🚦 Gates</div>
  <div style="margin-top:0.3rem;font-size:0.72rem;color:var(--fwd-text-muted);">
    <div><span style="color:var(--fwd-success);">✓ G0</span> Engine stable + 4h data → Phase 1</div>
    <div><span style="color:var(--fwd-success);">✓ G1</span> 1+ DSR-passed signal → Integration</div>
    <div><span style="color:var(--fwd-success);">✓ G2</span> 5 uncorrelated signals (ρ&lt;0.4) → Phase 2</div>
    <div><span style="color:var(--fwd-accent);">⟳ G3</span> 90d paper profit → Prop-Firm eval</div>
    <div>G4: Prop-Firm passed → Funded trading</div>
    <div>G5: 6mo funded profit → Copy + Scale</div>
  </div>
</div>

<!-- ── Capital Path ── -->
<div class="card glow-neutral" style="margin-top:0.5rem;">
  <div style="font-weight:600;color:var(--fwd-text-bright);">💰 Capital Path</div>
  <div style="margin-top:0.3rem;font-size:0.72rem;color:var(--fwd-text-muted);">
    <div>€500 @ 5x → fee-drag 77% → <span style="color:var(--fwd-danger);">not viable</span></div>
    <div>↓ 90d paper track record</div>
    <div>$25k @ 0.2x → fee-drag &lt;5% → <span style="color:var(--fwd-success);">viable</span></div>
    <div>↓ + copy trading</div>
    <div>$50k+ multi-signal → <span style="color:var(--fwd-accent);">$2k-4k/mo net</span></div>
  </div>
</div>

</div>