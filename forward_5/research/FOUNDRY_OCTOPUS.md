# Foundry V8 — Oktopus Architecture

## Konzept: 2026-04-27 (Final)

### Status: Sprint 1 IMPLEMENTIERT ✅

- ✅ `autopsy.py` — Autopsie-Modul (Asset/Window/Exit/Regime/Trade-Density-Analyse + gezielte Mutationen)
- ✅ `parameter_sweep.py` — Grid-Search + Regime-Overlay + Quick-WF Prefilter
- ✅ `run_evolution_v8.py` — Phase 2.5 (Sweep) + Phase 3.5 (Autopsie) integriert
- ✅ Test-Run: Sweep fand IS=+0.30, R=+2.09% mit bb_lower_14 + rsi_14<28 + ema_200 + adx_14>25
- ⬜ Sprint 2: Budget-Steuerung + 4h-Arm (nächster Schritt)

### Leitmotiv: Der Oktopus

Ein Oktopus hat Arme die halb-autonom tasten, aber ein zentrales Gehirn das koordiniert.
Arme die nichts finden werden eingezogen. Arme die fündig werden bekommen mehr Budget.
Fails werden nicht weggeworfen sondern autopsiert — das Lernen ist der Kern.

---

## Pipeline

```
                    ┌─────────────────────────────────┐
                    │         ZENTRALES GEHIRN         │
                    │   HOF + Muster-Erkenntnis        │
                    │   Budget-Steuerung               │
                    └──┬──┬──┬──┬──┬──┬───────────────┘
                       │  │  │  │  │  │
                    ┌──┘  │  │  │  │  └──┐
                    ▼     ▼  ▼  ▼  ▼     ▼
                  ARM1  ARM2 ARM3 ARM4 ARM5 ARM6
                   MR   Trend  Mom  Vol  Reg  4h
                   
  Jeder Arm: Discovery → Sweep → WF Gate → Autopsie → Feedback → Discovery
```

### Die 6 Arme (Start-Konfiguration)

| Arm | Typ | Fokus | Status |
|-----|------|-------|--------|
| 1 | Mean Reversion | BB/RSI/ZScore Oversold | Aktiv |
| 2 | Trend Following | EMA/ADX/MACD | Aktiv |
| 3 | Momentum | ROC/Breakout/Volume-Spike | Aktiv |
| 4 | Volume-Boosted | Volume-Confirm für alle Typen | Aktiv |
| 5 | Regime | BB-Width/ADX/ATR als Filter | Aktiv |
| 6 | 4h Timeframe | Gleiche Strategien auf 4h-Kerzen | NEU |

### Aufgeschobene Arme (bis 4h bewiesen)

| Arm | Typ | Warum aufgeschoben |
|-----|------|-------------------|
| 7 | 15m Scalping | Testnet-Daten dünn, Paper Engine pollt nur 60s, braucht engere Stops — riskant |
| 8 | Hybrid (1h+4h) | DSL Parser muss Timeframe-Qualifier lernen (ema_200_4h) — Aufwand hoch |

**Entscheidungsregel:** Arm 7+8 erst wenn Arm 6 (4h) einen Kandidaten mit IS>0 liefert.
Wenn 4h besser funktioniert als 1h, ist 15m ohnehin fragwürdig.
Wenn 4h auch nichts findet, bringt 15m wahrscheinlich auch nichts.

---

## Die 4+1 Phasen (pro Arm)

```
DISCOVERY → SWEEP → WF GATE → AUTOPSIE ──┐
                                              │
                          PASS → CONFIRM ←───┘
                          (10w Hard Check)   Feedback → Discovery
```

### Phase 1: Discovery (LLM)

- Jeder Arm hat eigenen Prompt mit passenden Indikatoren
- LLM generiert neue Strategie-Konzepte
- Budget pro Arm adaptiv (siehe Gehirn)
- Stärke: Findet neue IDEEN
- Schwäche: Parametrisierung zufällig

### Phase 2: Optimization (Sweep)

- Systematischer Grid-Search auf Kandidaten ab IS > -0.1
- Parameter: BB-Periode, RSI-Threshold, EMA-Perioden, Trail, SL, Max Hold
- Regime-Overlay als zusätzliche Dimension
- Quick-WF Prefilter (3-Window) um teure 10w-Runs zu sparen
- Stärke: Findet das OPTIMUM innerhalb eines Parameterraums
- Schwäche: Findet keine neuen Ideen

### Phase 3: Validation (WF Gate, 10-Window)

- 10-Window Walk-Forward auf optimierte Kandidaten
- Nur Top-N aus Sweep kommen hier rein (teuer!)
- **WF Gate erweitert**: Liefert jetzt Asset-Returns, Window-Returns, Exit-Reasons
  (notwendig für Autopsie)

### Phase 4: Autopsie (IMPLEMENTIERT ✅)

Analysiere WARUM ein Kandidat fiel und generiere gezielte Mutationen:

1. **Asset-Analyse**: Funktioniert auf BTC+ETH, fällt auf DOGE+ADA?
   → Mutation: BB-Width-Filter oder Asset-spezifische Parameter
2. **Window-Analyse**: Meist profitabel (z.B. 22/60)?
   → Mutation: Feintuning statt radikaler Umbau
3. **Exit-Analyse**: DD/Return-Ratio hoch → SL wird oft getroffen
   → Mutation: Trail +0.5%, SL +1.0%, Max Hold +12 bars
4. **Regime-Analyse**: Profitabel in Trend-Assets, verlustreich in Alts?
   → Mutation: ADX>20 oder ADX>25 als Filter
5. **Trade-Density**: <3 Trades/Window → Entry zu restriktiv
   → Mutation: RSI-Threshold lockern, weniger Filter
6. **Feed-Forward**: Gelernte Mutationen → `mutation_feed.json` für nächsten Run

**Implementierung:** `autopsy.py` — classify_strategy_type() + autopsie() + Entry-Modifier

**WF Gate Daten:** Aktuell nutzt Autopsie die vorhandenen WF-Ergebnisse (avg_oos_return, avg_trades, profitable_assets per Window). Exit-Reasons werden approximativ aus DD/Return-Ratio abgeleitet, da der WF Gate keine per-Trade Exit-Reasons speichert. Das reicht für eine erste Version — eine detaillierte Exit-Reason-Erfassung kann in Sprint 2 nachgezogen werden.

### Phase 5: Confirmation (10w Hard Check)

- Finale Bestätigung für WF-passed Kandidaten
- True Champion → bereit für Paper Trading

---

## Das zentrale Gehirn: Budget-Steuerung

```python
# Nach jedem Daily-Run berechne Arm-Performance:
arm_performance = {
    "MR":    {"candidates": 45, "wf_passed": 1, "avg_is": -0.08, "trend": "declining"},
    "Trend": {"candidates": 30, "wf_passed": 0, "avg_is": -0.45, "trend": "dead"},
    "4h":    {"candidates": 15, "wf_passed": 0, "avg_is": -0.05, "trend": "promising"},
}

# Budget-Anpassung (relativ zum Basis-Budget von 2 Kandidaten/Arm):
# - Arm mit wf_passed > 0:                Budget +50% (3 Kandidaten)
# - Arm mit avg_is > -0.1:               Budget +20% (nur nah dran lohnt sich)
# - Arm mit 50+ candidates, 0 wf_passed: Budget -50% (1 Kandidat)
# - Arm mit "dead" trend:                 Probe-Modus (1 Kandidat, kein Sweep)
# - Neuer Arm (erste 3 Tage):            Start-Budget +50% (3 Kandidaten)
```

Arme die nichts finden werden EINGEZOGEN.
Arme die fündig werden bekommen MEHR TENTAKELN.

### Trend-Erkennung

```python
def arm_trend(perf_history: list[dict]) -> str:
    """Bestimme Trend des Arms aus letzten 5 Runs."""
    recent_is = [p["avg_is"] for p in perf_history[-5:]]
    if not recent_is:
        return "new"
    
    # Linear regression auf avg_is
    slope = (recent_is[-1] - recent_is[0]) / len(recent_is)
    
    if max(recent_is) > 0:
        return "producing"      # Hat positive IS geliefert
    elif slope > 0.01:
        return "promising"      # Wird besser
    elif slope < -0.01:
        return "declining"      # Wird schlechter
    elif all(is_val < -0.3 for is_val in recent_is):
        return "dead"           # Hoffnungslos
    else:
        return "stable"         # Weder noch
```

---

## Autopsie-Modul (Detail)

```python
def autopsie(candidate: dict, wf_detail: dict) -> dict:
    """
    Analysiere WARUM ein Kandidat fiel.
    Generiere gezielte Mutationen basierend auf Erkenntnissen.
    
    Args:
        candidate: Strategie-Definition (entry, exit_config, etc.)
        wf_detail: Detaillierte WF-Ergebnisse vom erweiterten Gate
    
    Returns:
        {learnings: [...], mutations: [...], priority: "high"|"medium"|"low"}
    """
    learnings = []
    mutations = []
    
    # 1. Asset-Analyse
    per_asset = wf_detail.get("per_asset_returns", {})
    strong = [a for a, r in per_asset.items() if r > 0]
    weak = [a for a, r in per_asset.items() if r <= 0]
    if len(strong) > 0 and len(weak) > 0:
        learnings.append(f"Asset-Split: stark={strong}, schwach={weak}")
        # Mutation: Nur auf starken Assets traden (Asset-Whitelist)
        # ODER: Entry für schwache Assets lockern
    
    # 2. Window-Analyse
    per_window = wf_detail.get("per_window_returns", [])
    n_profitable = sum(1 for r in per_window if r > 0)
    if n_profitable >= 5:
        learnings.append(f"Nah dran: {n_profitable}/10 Windows profitabel")
        mutations.append({"type": "fine_tune", "msg": "Feintuning statt Umbau"})
    elif n_profitable >= 3:
        learnings.append(f"Teilprofitabel: {n_profitable}/10 Windows")
    
    # 3. Exit-Analyse
    exits = wf_detail.get("exit_reasons", {})
    sl_count = exits.get("stop_loss", 0)
    trail_count = exits.get("trailing_stop", 0)
    maxhold_count = exits.get("max_hold", 0)
    total = sl_count + trail_count + maxhold_count
    if total > 0:
        if sl_count > trail_count * 2:
            learnings.append(f"SL dominiert ({sl_count}/{total}) — Trail zu eng oder SL zu nah")
            mutations.append({
                "type": "exit_widen",
                "msg": "Trail +0.5%, SL +1.0%, Max Hold +12 bars"
            })
        if maxhold_count > total * 0.3:
            learnings.append(f"Max-Hold dominiert ({maxhold_count}/{total}) — Exit zu spät")
            mutations.append({
                "type": "exit_faster",
                "msg": "Trail -0.3%, Max Hold -6 bars"
            })
    
    # 4. Regime-Analyse
    # Wenn mehr als 60% der Trades in Trend-Phasen profitabel sind
    # aber in Range-Phasen verlieren → Regime-Filter
    trend_profit = wf_detail.get("trend_profit_rate", 0)
    range_profit = wf_detail.get("range_profit_rate", 0)
    if trend_profit > 0.5 and range_profit < 0.3:
        learnings.append("Profitabel in Trend, verlustreich in Range")
        mutations.append({
            "type": "add_regime_filter",
            "msg": "Füge adx_14 > 20 als Entry-Filter hinzu"
        })
    
    # 5. Priorität basierend auf Nähe zum Pass
    priority = "low"
    if n_profitable >= 5:
        priority = "high"   # Nah dran — priorisieren!
    elif n_profitable >= 3:
        priority = "medium"
    
    return {
        "learnings": learnings,
        "mutations": mutations,
        "priority": priority,
        "candidate_name": candidate.get("name", "?"),
    }
```

---

## Regime-Overlay-Dimension

Jeder Kandidat wird MIT und OHNE Regime-Filter getestet (im Sweep):

```python
REGIME_OVERLAYS = [
    {"name": "none",        "condition": None},
    {"name": "adx_trend",   "condition": "adx_14 > 20"},
    {"name": "adx_strong",  "condition": "adx_14 > 25"},
    {"name": "bb_squeeze",  "condition": "bb_width_20 < 0.03"},
    {"name": "low_vol",     "condition": "atr_14 < atr_14_sma"},
]
```

5x mehr IS-Backtests (billig), aber nur die beste Kombi zum teuren WF-Gate.
Autopsie bekommt die Regime-Ergebnisse mit und kann lernen: "ADX>20 hilft bei Trend-Strategien, nicht bei MR".

---

## Laufzeit-Budget pro Daily Run

| Phase | Dauer pro Kandidat | Anzahl | Gesamt |
|-------|-------------------|--------|--------|
| Discovery (LLM) | 10s | 6 Arme × 2 = 12 | ~2 min |
| IS-Backtest | 3s | 12 Kandidaten × 5 Regimes | ~3 min |
| Sweep (Grid) | 3s × 50 Params | Top-3 Kandidaten × 5 Regimes | ~8 min |
| Quick-WF (3-Window) | 30s | Top-10 | ~5 min |
| WF Gate (10-Window) | 2min | Top-3 | ~6 min |
| Autopsie | <1s | Alle WF-Fails | <1 min |
| 4h-Aggregation | — | 12 Kandidaten × 6 Assets | ~3 min |
| **Gesamt** | | | **~28 min** |

Machbar für einen 04:30 Cron. Wenn es länger dauert, kann man Quick-WF auf Top-5 reduzieren.

**Laufzeit-Management:** Der Sweep hat ein `max_combinations=200` Limit (random sampling bei über 200 Kombis). Das hält die Laufzeit vorhersehbar.

---

## Daily Run Ablauf

```
04:30 Cron startet

1. GEHIRN: Lade HOF + Arm-Performance, berechne Budgets pro Arm
2. Für jeden ARM:
   a. Discovery: N LLM-Calls je nach Budget
   b. IS-Backtest: Bewerte mit Gradient-Score + Regime-Overlay
   c. Sweep: Grid-Search auf Top-Kandidaten (IS > -0.1)
   d. Quick-WF: 3-Window Prefilter auf Sweep-Top
   e. WF Gate: 10-Window auf Quick-WF-Survivors
   f. Autopsie: Analysiere Fails → generiere gezielte Mutationen
3. GEHIRN: Update HOF, Arm-Performance, Budgets
4. MUTATION FEED: Autopsie-Mutationen → Arm Discovery (nächster Run)
5. HARD CHECK: 10w auf neue WF-Passes
6. REPORT: Discord Embed mit Arm-Performance + Learnings + Autopsie-Insights
```

---

## 4h-Timeframe (Arm 6)

### Aggregation

```python
def aggregate_1h_to_4h(df_1h: pl.DataFrame) -> pl.DataFrame:
    """Aggregiere 1h-Kerzen zu 4h-Kerzen."""
    return df_1h.group_by_dynamic(
        "timestamp", every="4h", label="left"
    ).agg([
        pl.col("open").first(),
        pl.col("high").max(),
        pl.col("low").min(),
        pl.col("close").last(),
        pl.col("volume").sum(),
    ])
```

### Keine neuen Daten nötig

4h wird aus bestehenden 1h-Daten aggregiert. Das bedeutet:
- Gleicher Datenbestand (2023-01 bis 2025-04)
- 5040 Kerzen statt 20160 (1/4)
- BB/RSI/EMA-Perioden sollten angepasst werden (z.B. BB_40 statt BB_20 für äquivalente Window-Größe)

### Paper Engine Kompatibilität

Wenn ein 4h-Champion gefunden wird, muss die Paper Engine angepasst werden:
- Data Feed: 4h-Kerzen aggregieren
- Position Sizing: Gleich (Capital / N Assets)
- Polling: Immer noch 60s, aber Entry-Signale nur alle 4h
- Das ist ein Paper Engine Change, aber erst relevant WENN ein 4h-Champion existiert

---

## Implementierungs-Reihenfolge

### Sprint 1: Autopsie + Sweep (IMPLEMENTIERT ✅)

| Schritt | Was | Datei | Status |
|---------|-----|-------|--------|
| 1.1 | WF Gate erweitern | walk_forward_gate.py | ⬜ (optional, Autopsie arbeitet mit vorhandenen Daten) |
| 1.2 | Autopsie-Modul | autopsy.py | ✅ Implementiert + getestet |
| 1.3 | Sweep-Modul (Grid + Regime-Overlay + Quick-WF) | parameter_sweep.py | ✅ Implementiert + getestet |
| 1.4 | V8 integrieren: Phase 2.5 + Phase 3.5 | run_evolution_v8.py | ✅ Integriert |
| 1.5 | Test-Run + Cron-Update | — | ✅ Sweep-Test: IS=+0.30, R=+2.09% |

### Sprint 2: Budget + 4h (IMPLEMENTIERT ✅)

| Schritt | Was | Status |
|---------|-----|--------|
| 2.1 | Arm-Performance Tracking | ✅ `arm_performance.json` |
| 2.2 | Budget-Steuerung (dead→probe, producing→extra) | ✅ In V8 integriert |
| 2.3 | 4h-Aggregation + Arm 6 Prompt | ✅ `aggregate_to_4h()` + 4H Prompt |
| 2.4 | V8 Test + Syntax-Check | ✅ Alle Syntax-Checks bestanden |

### Sprint 3: Evaluierung (Tag 7-9)

| Schritt | Was |
|---------|-----|
| 3.1 | 5+ Daily Runs ausgewertet |
| 3.2 | Arm-Performance-Report |
| 3.3 | Entscheidung: 15m-Arm? Hybrid? |
| 3.4 | Foundry Review (~09.05.) |

---

## Unterschied V8-aktuell → Oktopus

| V8-aktuell | Oktopus |
|------------|---------|
| 5 Typen, feste Budgets | 6 Arme, adaptive Budgets |
| Mutation = "ändere irgendwas" | Mutation = Autopsie-gesteuert |
| Fail = wegwerfen | Fail = lernen |
| Nur 1h | 1h + 4h |
| Kein Sweep | Grid-Search + Regime-Overlay |
| WF Gate liefert nur Pass/Fail | WF Gate liefert detaillierte Autopsie-Daten |
| Lineare Pipeline | Zyklisch mit Feedback |