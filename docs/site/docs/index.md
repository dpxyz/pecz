---
title: Mission Control
---

<div class="dashboard">

<!-- ── Header ── -->
<div class="dash-header">
<h1><span class="logo"><svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><polygon points="5,0.5 9.5,9.5 0.5,9.5"/></svg><svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><circle cx="5" cy="5" r="4.2"/></svg><svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><rect x="0.8" y="0.8" width="8.4" height="8.4"/></svg></span>PECZ<span class="accent">_</span></h1>
<div class="dash-meta">
<span><span class="live-dot"></span>PHASE 8 LIVE</span>
<span>DAY 3/14</span>
<span id="dash-timestamp">⏳</span>
<span>EQ 99.49€</span>
</div>
</div>

<!-- ── System Status ── -->
<div class="section-label">system</div>
<div class="grid-3">

<div class="card glow-success status-card">
  <div>
    <div class="status-label">engine</div>
    <div class="status-sub">paper · rest · 60s</div>
  </div>
  <span class="badge badge--success">● run</span>
</div>

<div class="card glow-success status-card">
  <div>
    <div class="status-label">watchdog</div>
    <div class="status-sub">v2 · breaker · 1h</div>
  </div>
  <span class="badge badge--success">● ok</span>
</div>

<div class="card glow-success status-card">
  <div>
    <div class="status-label">database</div>
    <div class="status-sub">30.1k candles · 6 assets</div>
  </div>
  <span class="badge badge--success">● ok</span>
</div>

</div>

<!-- ── Key Metrics ── -->
<div class="section-label">metrics</div>
<div class="grid-4">

<div class="card metric-card">
  <div class="metric-label">equity</div>
  <div class="metric-value">99.49€</div>
  <div class="metric-sub">start: 100.00€</div>
</div>

<div class="card metric-card">
  <div class="metric-label">pnl</div>
  <div class="metric-value negative">-0.51€</div>
  <div class="metric-sub">net · fees deducted</div>
</div>

<div class="card metric-card">
  <div class="metric-label">trades</div>
  <div class="metric-value">6</div>
  <div class="progress-bar"><div class="progress-fill accent" style="width:60%"></div></div>
  <div class="metric-sub">target: ≥10</div>
</div>

<div class="card metric-card">
  <div class="metric-label">drawdown</div>
  <div class="metric-value">0.51%</div>
  <div class="progress-bar"><div class="progress-fill success" style="width:2%"></div></div>
  <div class="metric-sub">limit: ≤25%</div>
</div>

</div>

<!-- ── Equity Curve ── -->
<div class="section-label">equity curve</div>
<div class="chart-area">
<div class="chart-icon">📈</div>
<div class="chart-text">monitor_v1 — pending implementation</div>
</div>

<!-- ── Phase Timeline ── -->
<div class="section-label">roadmap</div>
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

<!-- ── Open Position ── -->
<div class="section-label">open position</div>

| asset | side | entry | size | lev | status |
|-------|------|-------|------|-----|--------|
| BTC | LONG | $76,426 | 0.000391 | 1.8x | ● open |
| ETH | LONG | $2,412 | 0.012371 | 1.8x | ● open |
| SOL | LONG | $88.38 | 0.281422 | 1.5x | ● open |
| AVAX | LONG | $9.59 | 1.729173 | 1.0x | ● open |
| DOGE | LONG | $0.10 | 253.357408 | 1.5x | ● open |
| ADA | LONG | $0.25 | 97.701401 | 1.5x | ● open |

<!-- ── Quick Navigation ── -->
<div class="section-label">docs</div>
<div class="grid-6">

<a href="roadmap/" class="quick-link">
  <span class="link-icon">🗺️</span>
  <div class="link-text">roadmap<span class="link-desc">phases & milestones</span></div>
</a>

<a href="economics/" class="quick-link">
  <span class="link-icon">💰</span>
  <div class="link-text">economics<span class="link-desc">costs & break-even</span></div>
</a>

<a href="dashboard/" class="quick-link">
  <span class="link-icon">📊</span>
  <div class="link-text">live monitor<span class="link-desc">quity curve + chart</span></div>
</a>

<a href="test-suite/" class="quick-link">
  <span class="link-icon">🧪</span>
  <div class="link-text">test-suite<span class="link-desc">297 tests · 81% cov</span></div>
</a>

<a href="architecture/adr-005/" class="quick-link">
  <span class="link-icon">🏗️</span>
  <div class="link-text">architecture<span class="link-desc">three-layer adr</span></div>
</a>

<a href="strategy-lab/baseline/" class="quick-link">
  <span class="link-icon">🔬</span>
  <div class="link-text">baseline<span class="link-desc">adx+ema gold standard</span></div>
</a>

<a href="v2-design/" class="quick-link">
  <span class="link-icon">🔮</span>
  <div class="link-text">v2-design<span class="link-desc">regime & sentiment</span></div>
</a>

</div>

<script>
(function() {
  const DATA_URL = 'https://raw.githubusercontent.com/dpxyz/pecz/main/forward_5/executor/monitor_data.json';
  async function updateTimestamp() {
    try {
      const resp = await fetch(DATA_URL + '?t=' + Date.now());
      if (!resp.ok) return;
      const data = await resp.json();
      const ts = data.generated_at || data.summary?.timestamp;
      if (!ts) return;
      const d = new Date(ts);
      const el = document.getElementById('dash-timestamp');
      if (el) el.textContent = d.toLocaleTimeString('de-DE', {hour:'2-digit', minute:'2-digit'}) + ' · ' + d.toLocaleDateString('de-DE', {day:'2-digit', month:'2-digit'});
    } catch(e) {}
  }
  updateTimestamp();
  setInterval(updateTimestamp, 300000);
})();
</script>

</div>