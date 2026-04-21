---
title: Mission Control
custom_css:
  - stylesheets/dashboard.css
---

<div class="dashboard">

<!-- ── Header ── -->
<div class="dash-header">
<h1>🎯 Forward V5</h1>
<span class="dash-phase">Phase 8 ⭐ LIVE · Day 2/14 · Equity: 99.99€</span>
</div>

<!-- ── Status Board ── -->
<p class="section-title">System Status</p>
<div class="grid-3">

<div class="status-card">
  <div>
    <div class="label">Engine</div>
    <div class="sublabel">Paper Trading, REST Polling</div>
  </div>
  <span class="badge badge--success">🟢 RUNNING</span>
</div>

<div class="status-card">
  <div>
    <div class="label">Watchdog V2</div>
    <div class="sublabel">Hourly check, circuit breaker</div>
  </div>
  <span class="badge badge--success">✅ OK</span>
</div>

<div class="status-card">
  <div>
    <div class="label">Database</div>
    <div class="sublabel">30,144 candles</div>
  </div>
  <span class="badge badge--success">✅ HEALTHY</span>
</div>

</div>

<!-- ── Key Metrics ── -->
<p class="section-title">Key Metrics</p>
<div class="grid-4">

<div class="metric-card">
  <div class="metric-label">Equity</div>
  <div class="metric-value">99.99€</div>
  <div class="metric-sub">Start: 100.00€</div>
</div>

<div class="metric-card">
  <div class="metric-label">P&L</div>
  <div class="metric-value positive">+0.00€</div>
  <div class="metric-sub">Fees deducted</div>
</div>

<div class="metric-card">
  <div class="metric-label">Trades</div>
  <div class="metric-value">2</div>
  <div class="metric-sub">Target: ≥10</div>
</div>

<div class="metric-card">
  <div class="metric-label">Drawdown</div>
  <div class="metric-value">0.01%</div>
  <div class="metric-sub">Limit: ≤25%</div>
</div>

</div>

<!-- ── Equity Curve ── -->
<p class="section-title">Equity Curve</p>
<div class="chart-placeholder">
<span class="material-icons">show_chart</span><br>
📈 Monitor V1 — Live equity chart coming soon
</div>

<!-- ── Phase Timeline ── -->
<p class="section-title">Roadmap</p>
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

<!-- ── Open Position ── -->
<p class="section-title">Open Positions</p>

| Asset | Side | Entry | Size | Leverage | Status |
|-------|------|-------|------|----------|--------|
| BTC | LONG | $76,567 | 0.000392 | 1.8x | 🟢 Open |

<!-- ── Quick Navigation ── -->
<p class="section-title">Documentation</p>
<div class="grid-3">

<a href="roadmap/" class="quick-link">
  <span class="material-icons">map</span>
  <div>
    <div>Roadmap</div>
    <div class="link-desc">Phases, milestones, progress</div>
  </div>
</a>

<a href="economics/" class="quick-link">
  <span class="material-icons">euro</span>
  <div>
    <div>Economics</div>
    <div class="link-desc">Costs, break-even, fees</div>
  </div>
</a>

<a href="test-suite/" class="quick-link">
  <span class="material-icons">checklist</span>
  <div>
    <div>Test Suite</div>
    <div class="link-desc">110 tests, 100% pass</div>
  </div>
</a>

<a href="architecture/adr-005/" class="quick-link">
  <span class="material-icons">layers</span>
  <div>
    <div>Three-Layer ADR</div>
    <div class="link-desc">Foundry → Executor → Monitor</div>
  </div>
</a>

<a href="strategy-lab/baseline/" class="quick-link">
  <span class="material-icons">science</span>
  <div>
    <div>Baseline Strategy</div>
    <div class="link-desc">ADX+EMA MACD gold standard</div>
  </div>
</a>

<a href="v2-design/" class="quick-link">
  <span class="material-icons">auto_awesome</span>
  <div>
    <div>V2 Design</div>
    <div class="link-desc">Regime, volatility, sentiment</div>
  </div>
</a>

</div>

</div>