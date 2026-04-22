---
title: Dashboard
hide:
  - navigation
  - toc
---

# 📊 Live Dashboard

<div id="monitor-last-update" style="float:right; color:var(--fwd-text-muted); font-size:0.85rem; font-family:var(--fwd-font);">⏳</div>

<div style="clear:both;"></div>

<div id="monitor-loading" style="text-align:center; padding:4rem 0;">
  <div style="font-size:2rem;">⏳</div>
  <div style="color:var(--fwd-text-muted); margin-top:0.5rem;">Loading monitor data…</div>
</div>

<div id="monitor-dashboard" style="display:none;">

<!-- Summary Cards -->
<div class="grid-4" id="summary-cards">
  <div class="card metric-card">
    <div class="metric-label">equity</div>
    <div class="metric-value" id="eq-value">—</div>
    <div class="metric-sub" id="eq-sub">start: 100.00€</div>
  </div>
  <div class="card metric-card">
    <div class="metric-label">pnl</div>
    <div class="metric-value" id="pnl-value">—</div>
    <div class="metric-sub">net · fees deducted</div>
  </div>
  <div class="card metric-card">
    <div class="metric-label">drawdown</div>
    <div class="metric-value" id="dd-value">—</div>
    <div class="metric-sub">limit: ≤25%</div>
  </div>
  <div class="card metric-card">
    <div class="metric-label">trades</div>
    <div class="metric-value" id="trades-value">—</div>
    <div class="metric-sub" id="trades-sub">target: ≥10</div>
  </div>
</div>

<!-- Equity Curve -->
<div class="section-label">equity curve</div>
<div class="chart-area" style="min-height:280px; position:relative;">
  <canvas id="equity-chart"></canvas>
</div>

<!-- Drawdown Curve -->
<div class="section-label">drawdown</div>
<div class="chart-area" style="min-height:140px; position:relative;">
  <canvas id="dd-chart"></canvas>
</div>

<!-- Open Positions -->
<div class="section-label">open positions</div>
<div id="positions-grid" class="grid-2" style="gap:0.5rem;">
  <div class="card" style="color:var(--fwd-text-muted); font-size:0.85rem; text-align:center; padding:1rem;">
    Loading…
  </div>
</div>

<!-- Recent Trades -->
<div class="section-label">recent trades</div>
<div id="trades-grid" class="grid-2" style="gap:0.5rem;">
  <div class="card" style="color:var(--fwd-text-muted); font-size:0.85rem; text-align:center; padding:1rem;">
    No trades yet.
  </div>
</div>

</div>

<!-- Guard State Banner -->
<div id="guard-banner" style="display:none; margin:1rem 0; padding:0.75rem 1rem; border-radius:6px; font-family:var(--fwd-font); font-weight:600; font-size:0.9rem;"></div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script>
(function() {
  const DATA_URL = 'monitor_data.json';
  const PALETTE = {
    accent: '#D4FF5F',
    danger: '#FF5F5F',
    warning: '#FFB05F',
    text: '#C9C3BB',
    muted: '#6B6560',
    surface: '#1F1C1A',
    border: '#352F2C',
    bg: '#161412',
  };

  let equityChart = null;
  let ddChart = null;

  async function load() {
    try {
      const resp = await fetch(DATA_URL + '?t=' + Date.now());
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      render(data);
    } catch(e) {
      document.getElementById('monitor-loading').innerHTML =
        '<div style="color:var(--fwd-danger);">⚠️ Failed to load monitor data</div>' +
        '<div style="color:var(--fwd-text-muted); font-size:0.8rem; margin-top:0.5rem;">' + e.message + '</div>';
    }
  }

  function fmt(v, decimals=2) { return v != null ? v.toFixed(decimals) : '—'; }
  function fmtEur(v) { return fmt(v) + '€'; }
  function fmtPct(v) { return fmt(v) + '%'; }

  function render(data) {
    document.getElementById('monitor-loading').style.display = 'none';
    document.getElementById('monitor-dashboard').style.display = 'block';

    const s = data.summary;
    const pnl = s.pnl || 0;

    // Summary cards
    document.getElementById('eq-value').textContent = fmtEur(s.equity);
    document.getElementById('eq-sub').textContent = 'start: ' + fmtEur(s.start_equity);

    const pnlEl = document.getElementById('pnl-value');
    pnlEl.textContent = (pnl >= 0 ? '+' : '') + fmtEur(pnl);
    pnlEl.style.color = pnl >= 0 ? PALETTE.accent : PALETTE.danger;

    const ddEl = document.getElementById('dd-value');
    ddEl.textContent = fmtPct(s.drawdown_pct);
    ddEl.style.color = s.drawdown_pct > 15 ? PALETTE.danger : s.drawdown_pct > 10 ? PALETTE.warning : PALETTE.accent;

    document.getElementById('trades-value').textContent = s.total_trades;
    document.getElementById('trades-sub').textContent = s.wins + 'W/' + s.losses + 'L · ' + fmt(s.win_rate, 0) + '%';

    // Guard banner
    if (s.guard_state !== 'RUNNING') {
      const banner = document.getElementById('guard-banner');
      banner.style.display = 'block';
      banner.style.background = s.guard_state === 'KILL_SWITCH' ? 'rgba(255,95,95,0.15)' : 'rgba(255,176,95,0.15)';
      banner.style.color = s.guard_state === 'KILL_SWITCH' ? PALETTE.danger : PALETTE.warning;
      banner.style.border = '1px solid ' + (s.guard_state === 'KILL_SWITCH' ? PALETTE.danger : PALETTE.warning);
      banner.textContent = '🛑 Guard: ' + s.guard_state;
    }

    // Timestamp in header
    const tsEl = document.getElementById('monitor-last-update');
    if (tsEl && data.generated_at) {
      const d = new Date(data.generated_at);
      tsEl.textContent = d.toLocaleDateString('de-DE', {day:'2-digit', month:'2-digit'}) + ' · ' + d.toLocaleTimeString('de-DE', {hour:'2-digit', minute:'2-digit'});
    }

    // Equity chart
    renderEquityChart(data.equity_curve);

    // DD chart
    renderDDChart(data.equity_curve);

    // Positions
    renderPositions(data.positions);

    // Recent trades
    renderTrades(data.recent_trades);
  }

  function renderEquityChart(curve) {
    if (!curve || curve.length === 0) return;
    const labels = curve.map(p => {
      const d = new Date(p.ts);
      return d.toLocaleDateString('de-DE', {day:'2-digit', month:'2-digit'}) + ' ' +
             d.toLocaleTimeString('de-DE', {hour:'2-digit', minute:'2-digit'});
    });
    const equityData = curve.map(p => p.equity + (p.unrealized_pnl || 0));

    const ctx = document.getElementById('equity-chart').getContext('2d');
    if (equityChart) equityChart.destroy();
    equityChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'Equity (MTM)',
          data: equityData,
          borderColor: PALETTE.accent,
          backgroundColor: 'rgba(212,255,95,0.08)',
          borderWidth: 2,
          fill: true,
          pointRadius: curve.length < 50 ? 3 : 0,
          pointBackgroundColor: PALETTE.accent,
          tension: 0.3,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: PALETTE.surface,
            titleColor: PALETTE.text,
            bodyColor: PALETTE.text,
            borderColor: PALETTE.border,
            borderWidth: 1,
            callbacks: {
              label: (ctx) => fmtEur(ctx.parsed.y),
            }
          }
        },
        scales: {
          x: {
            ticks: { color: PALETTE.muted, maxTicksLimit: 8, font: {size:10} },
            grid: { color: 'rgba(53,47,44,0.5)' },
          },
          y: {
            ticks: { color: PALETTE.muted, callback: v => fmtEur(v), font: {size:10} },
            grid: { color: 'rgba(53,47,44,0.5)' },
          }
        }
      }
    });
  }

  function renderDDChart(curve) {
    if (!curve || curve.length === 0) return;
    const labels = curve.map(p => {
      const d = new Date(p.ts);
      return d.toLocaleDateString('de-DE', {day:'2-digit', month:'2-digit'}) + ' ' +
             d.toLocaleTimeString('de-DE', {hour:'2-digit', minute:'2-digit'});
    });
    const ddData = curve.map(p => -(p.drawdown_pct || 0));

    const ctx = document.getElementById('dd-chart').getContext('2d');
    if (ddChart) ddChart.destroy();
    ddChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'Drawdown',
          data: ddData,
          borderColor: PALETTE.danger,
          backgroundColor: 'rgba(255,95,95,0.08)',
          borderWidth: 2,
          fill: true,
          pointRadius: curve.length < 50 ? 3 : 0,
          tension: 0.3,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: PALETTE.surface,
            titleColor: PALETTE.text,
            bodyColor: PALETTE.text,
            borderColor: PALETTE.border,
            borderWidth: 1,
            callbacks: {
              label: (ctx) => fmtPct(Math.abs(ctx.parsed.y)),
            }
          }
        },
        scales: {
          x: {
            ticks: { color: PALETTE.muted, maxTicksLimit: 8, font: {size:10} },
            grid: { color: 'rgba(53,47,44,0.5)' },
          },
          y: {
            ticks: { color: PALETTE.muted, callback: v => fmtPct(Math.abs(v)), font: {size:10} },
            grid: { color: 'rgba(53,47,44,0.5)' },
          }
        }
      }
    });
  }

  function smartDec(v) {
    if (v == null) return '—';
    if (v < 1) return v.toFixed(6);
    if (v < 100) return v.toFixed(4);
    return v.toFixed(2);
  }

  function renderPositions(positions) {
    const grid = document.getElementById('positions-grid');
    if (!positions || positions.length === 0) {
      grid.innerHTML = '<div class="card" style="color:var(--fwd-text-muted); font-size:0.85rem; text-align:center; padding:1rem;">No open positions</div>';
      return;
    }
    grid.innerHTML = positions.map(p => {
      const sym = p.symbol.replace('USDT', '');
      const upnl = p.unrealized_pnl || 0;
      const pnlColor = upnl >= 0 ? PALETTE.accent : PALETTE.danger;
      const pnlSign = upnl >= 0 ? '+' : '';
      const ep = smartDec(p.entry_price);
      const mp = smartDec(p.mark_price);
      return `<div class="card" style="padding:0.6rem 0.8rem;">` +
        `<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.3rem;">` +
          `<span style="color:var(--fwd-text-bright); font-weight:600;">${sym}</span>` +
          `<span style="color:${pnlColor}; font-weight:600;">${pnlSign}${fmtEur(upnl)}</span>` +
        `</div>` +
        `<div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--fwd-text-muted);">` +
          `<span>entry ${ep}</span>` +
          `<span>mark ${mp}</span>` +
        `</div>` +
      `</div>`;
    }).join('');
  }

  function renderTrades(trades) {
    const grid = document.getElementById('trades-grid');
    if (!trades || trades.length === 0) {
      grid.innerHTML = '<div class="card" style="color:var(--fwd-text-muted); font-size:0.85rem; text-align:center; padding:1rem;">No trades yet.</div>';
      return;
    }
    const exits = trades.filter(t => t.event === 'EXIT' || t.event === 'ENTRY');
    if (exits.length === 0) {
      grid.innerHTML = '<div class="card" style="color:var(--fwd-text-muted); font-size:0.85rem; text-align:center; padding:1rem;">No completed trades yet.</div>';
      return;
    }
    grid.innerHTML = exits.map(t => {
      const sym = t.symbol.replace('USDT', '');
      const pnl = t.pnl || 0;
      const pnlColor = pnl >= 0 ? PALETTE.accent : PALETTE.danger;
      const isEntry = t.event === 'ENTRY';
      const icon = isEntry ? '🟢' : '🔴';
      const ts = new Date(t.timestamp * 1000);
      const dateStr = ts.toLocaleDateString('de-DE', {day:'2-digit', month:'2-digit'});
      const timeStr = ts.toLocaleTimeString('de-DE', {hour:'2-digit', minute:'2-digit'});
      const dec = t.price < 1 ? 6 : (t.price < 100 ? 4 : 2);
      const pnlStr = !isEntry ? `<span style="color:${pnlColor}; font-weight:600;">${pnl >= 0 ? '+' : ''}${fmtEur(pnl)}</span>` : '';
      return `<div class="card" style="padding:0.5rem 0.8rem;">` +
        `<div style="display:flex; justify-content:space-between; align-items:center;">` +
          `<span>${icon} <span style="font-weight:600;">${sym}</span> <span style="color:var(--fwd-text-muted);">${t.event.toLowerCase()}</span></span>` +
          pnlStr +
        `</div>` +
        `<div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--fwd-text-muted); margin-top:0.15rem;">` +
          `<span>@ ${t.price.toFixed(dec)}</span>` +
          `<span>${dateStr} ${timeStr}</span>` +
        `</div>` +
      `</div>`;
    }).join('');
  }

  load();
  // Refresh every 5 minutes
  setInterval(load, 300000);
})();
</script>