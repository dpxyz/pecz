---
title: Mission Control
---

<div class="dashboard">

<!-- ── Header ── -->
<div class="dash-header">
<h1><span class="logo"><svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><polygon points="5,0.5 9.5,9.5 0.5,9.5"/></svg><svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><circle cx="5" cy="5" r="4.2"/></svg><svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><rect x="0.8" y="0.8" width="8.4" height="8.4"/></svg></span>PECZ<span class="accent">_</span></h1>
<div class="dash-meta">
<span><span class="live-dot"></span>V2 PAPER TRADING</span>
<span id="dash-day">—</span>
<span id="dash-timestamp">⏳</span>
</div>
</div>

<!-- ── System Status (compact) ── -->
<div class="section-label">system</div>
<div class="grid-3" style="gap:0.3rem;">

<div class="card status-compact">
  <div>
    <div class="status-label">engine</div>
    <div class="status-sub">V2 · funding-first · 60s</div>
  </div>
  <span class="badge-sm" style="color:var(--fwd-success);">● run</span>
</div>

<div class="card status-compact">
  <div>
    <div class="status-label">watchdog</div>
    <div class="status-sub">v2 · breaker · 1h</div>
  </div>
  <span class="badge-sm" style="color:var(--fwd-success);">● ok</span>
</div>

<div class="card status-compact">
  <div>
    <div class="status-label">database</div>
    <div class="status-sub">3 assets · BTC+ETH+SOL</div>
  </div>
  <span class="badge-sm" style="color:var(--fwd-success);">● ok</span>
</div>

</div>

<!-- ── Key Metrics ── -->
<div class="section-label">metrics</div>
<div class="grid-2">

<div class="card metric-card">
  <div class="metric-label">equity</div>
  <div class="metric-value" id="idx-equity">—</div>
  <div class="metric-sub">start: 100.00€</div>
</div>

<div class="card metric-card">
  <div class="metric-label">mtm equity</div>
  <div class="metric-value" id="idx-mtm">—</div>
  <div class="metric-sub">incl. unrealized</div>
</div>

<div class="card metric-card">
  <div class="metric-label">realized pnl</div>
  <div class="metric-value" id="idx-pnl">—</div>
  <div class="metric-sub">net · fees deducted</div>
</div>

<div class="card metric-card">
  <div class="metric-label">unrealized pnl</div>
  <div class="metric-value" id="idx-upnl">—</div>
  <div class="metric-sub">open positions</div>
</div>

<div class="card metric-card">
  <div class="metric-label">trades</div>
  <div class="metric-value" id="idx-trades">—</div>
  <div class="metric-sub" id="idx-trades-sub">target: ≥10</div>
</div>

<div class="card metric-card">
  <div class="metric-label">drawdown</div>
  <div class="metric-value" id="idx-dd">—</div>
  <div class="metric-sub">limit: ≤25%</div>
</div>

</div>

<!-- ── Equity Curve ── -->
<div class="section-label">equity curve</div>
<div class="chart-area" style="min-height:220px;position:relative;">
  <canvas id="index-equity-chart"></canvas>
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
  <div class="step-sublabel">V2 paper</div>
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

<!-- ── Open Positions (cards) ── -->
<div class="section-label">positions</div>
<div id="index-positions" class="grid-2" style="gap:0.5rem;">
  <div class="card" style="color:var(--fwd-text-muted);font-size:0.85rem;text-align:center;padding:1rem;">
    Loading…
  </div>
</div>

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
  <div class="link-text">live monitor<span class="link-desc">equity curve + chart</span></div>
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

</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script>
(function() {
  const DATA_URL = '/monitor_data.json';
  const P = {accent:'#D4FF5F',danger:'#FF5F5F',text:'#C9C3BB',muted:'#6B6560',surface:'#1F1C1A',border:'#352F2C'};
  let eqChart = null;

  function smartDec(v) {
    if (v == null) return '—';
    if (v < 1) return v.toFixed(6);
    if (v < 100) return v.toFixed(4);
    return v.toFixed(2);
  }
  function fmtEur(v) { return v.toFixed(2) + '€'; }

  function updateIdxTimer(el) {
    const ts = el.getAttribute('data-entry-ts');
    if (!ts) return;
    const entry = new Date(typeof ts === 'string' && ts.includes('T') ? ts : Number(ts));
    if (isNaN(entry.getTime())) return;
    const diff = Date.now() - entry.getTime();
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    el.textContent = (h > 0 ? h + 'h ' : '') + m + 'm';
    if (diff > 48*3600000) el.style.color = P.danger;
    else if (h >= 24) el.style.color = '#FFB05F';
  }
  setInterval(() => document.querySelectorAll('.pos-timer').forEach(el => updateIdxTimer(el)), 60000);

  async function load() {
    try {
      const resp = await fetch(DATA_URL + '?t=' + Date.now());
      if (!resp.ok) return;
      const data = await resp.json();
      const s = data.summary || {};

      // Timestamp
      const ts = data.generated_at || s.timestamp;
      if (ts) {
        const d = new Date(ts);
        const el = document.getElementById('dash-timestamp');
        if (el) el.textContent = d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit'}) + ' · ' + d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
      }

      // Metrics
      const eqEl = document.getElementById('idx-equity');
      if (eqEl) eqEl.textContent = fmtEur(s.equity);

      const mtmEl = document.getElementById('idx-mtm');
      if (mtmEl) mtmEl.textContent = fmtEur(s.mtm_equity || s.equity);

      const pnlEl = document.getElementById('idx-pnl');
      if (pnlEl) {
        const pnl = s.pnl || 0;
        pnlEl.textContent = (pnl >= 0 ? '+' : '') + fmtEur(pnl);
        pnlEl.style.color = pnl >= 0 ? P.accent : P.danger;
      }

      const upnlEl = document.getElementById('idx-upnl');
      if (upnlEl) {
        const upnl = s.unrealized_pnl || 0;
        upnlEl.textContent = (upnl >= 0 ? '+' : '') + fmtEur(upnl);
        upnlEl.style.color = upnl >= 0 ? P.accent : P.danger;
      }

      const trEl = document.getElementById('idx-trades');
      if (trEl) trEl.textContent = s.total_trades != null ? s.total_trades : '—';
      const trSub = document.getElementById('idx-trades-sub');
      if (trSub) trSub.textContent = (s.wins||0) + 'W/' + (s.losses||0) + 'L · target: ≥10';

      const ddEl = document.getElementById('idx-dd');
      if (ddEl) {
        ddEl.textContent = s.drawdown_pct != null ? s.drawdown_pct.toFixed(2) + '%' : '—';
        ddEl.style.color = s.drawdown_pct > 15 ? P.danger : s.drawdown_pct > 10 ? '#FFB05F' : P.accent;
      }

      // Equity curve
      const curve = data.equity_curve || [];
      if (curve.length > 0) {
        const labels = curve.map(p => {
          const d = new Date(p.ts);
          return d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit'}) + ' ' + d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
        });
        const eqData = curve.map(p => p.equity + (p.unrealized_pnl||0));
        const ctx = document.getElementById('index-equity-chart');
        if (ctx) {
          if (eqChart) eqChart.destroy();
          eqChart = new Chart(ctx.getContext('2d'), {
            type:'line',
            data:{labels,datasets:[{label:'Equity',data:eqData,borderColor:P.accent,backgroundColor:'rgba(212,255,95,0.08)',borderWidth:2,fill:true,pointRadius:curve.length<50?3:0,tension:0.3}]},
            options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{backgroundColor:P.surface,titleColor:P.text,bodyColor:P.text,borderColor:P.border,borderWidth:1,callbacks:{label:c=>fmtEur(c.parsed.y)}}},scales:{x:{ticks:{color:P.muted,maxTicksLimit:6,font:{size:9}},grid:{color:'rgba(53,47,44,0.4)'}},y:{ticks:{color:P.muted,callback:v=>fmtEur(v),font:{size:9}},grid:{color:'rgba(53,47,44,0.4)'}}}}
          });
        }
      }

      // Positions as cards
      const positions = data.positions || [];
      const grid = document.getElementById('index-positions');
      if (positions.length === 0) {
        grid.innerHTML = '<div class="card" style="color:var(--fwd-text-muted);font-size:0.85rem;text-align:center;padding:1rem;">No open positions</div>';
      } else {
        grid.innerHTML = positions.map(p => {
          const sym = p.symbol.replace('USDT','');
          const side = (p.side || 'LONG').toUpperCase();
          const sideColor = side === 'LONG' ? P.accent : P.danger;
          const sideBg = side === 'LONG' ? 'rgba(212,255,95,0.12)' : 'rgba(255,95,95,0.12)';
          const lev = p.leverage ? p.leverage.toFixed(1) + 'x' : '';
          const upnl = p.unrealized_pnl || 0;
          const pc = upnl >= 0 ? P.accent : P.danger;
          const ps = upnl >= 0 ? '+' : '';
          return '<div class="card" style="padding:0.5rem 0.8rem;">' +
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.2rem;">' +
              '<span><span style="color:var(--fwd-text-bright);font-weight:600;">' + sym + '</span> <span style="font-size:0.6rem;font-weight:700;color:' + sideColor + ';background:' + sideBg + ';padding:1px 5px;border-radius:3px;margin-left:4px;">' + side + '</span>' + (lev ? '<span style="font-size:0.58rem;color:var(--fwd-text-dim);margin-left:6px;">' + lev + '</span>' : '') + '</span>' +
              '<span style="color:' + pc + ';font-weight:600;">' + ps + fmtEur(upnl) + '</span>' +
            '</div>' +
            '<div style="display:flex;justify-content:space-between;font-size:0.72rem;color:var(--fwd-text-muted);">' +
              '<span>entry ' + smartDec(p.entry_price) + '</span>' +
              '<span>mark ' + smartDec(p.mark_price) + '</span>' +
            '</div>' +
            '<div style="display:flex;justify-content:space-between;font-size:0.68rem;margin-top:0.15rem;">' +
              '<span style="color:var(--fwd-text-muted);">' + (p.entry_ts ? new Date(typeof p.entry_ts==="string"&&p.entry_ts.includes("T")?p.entry_ts:Number(p.entry_ts)).toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit'})+' '+new Date(typeof p.entry_ts==="string"&&p.entry_ts.includes("T")?p.entry_ts:Number(p.entry_ts)).toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'}) : '') + '</span>' +
              '<span style="color:var(--fwd-text-dim);" data-entry-ts="' + (p.entry_ts||'') + '" class="pos-timer"></span>' +
            '</div>' +
          '</div>';
        }).join('');
        document.querySelectorAll('.pos-timer').forEach(el => updateIdxTimer(el));
      }
    } catch(e) {}
  }
  // Dynamic day counter (V2 paper trading start: 2026-05-03)
  (function() {
    const start = new Date('2026-05-03T00:00:00+02:00');
    const now = new Date();
    const day = Math.floor((now - start) / 86400000) + 1;
    const el = document.getElementById('dash-day');
    if (el) el.textContent = 'DAY ' + Math.max(day,1) + '/14';
  })();

  load();
  setInterval(load, 300000);
})();
</script>