# PROJECT_STATUS.md — Detaillierter Projektstand

**Zuletzt aktualisiert:** 2026-05-05  
**Automatischer Verweis:** MEMORY.md → dieses Dokument für Details

---

## Daten-Inventar (verifiziert 2026-05-05)

| Datensatz | Datei | Zeilen | Zeitraum | Details |
|-----------|-------|--------|----------|---------|
| OI+LS+Taker Backfill | `data/bn_metrics_{asset}_1h.parquet` | 17.593 × 6 | 2024-05-01 → 2026-05-04 | 2 Jahre! sum_oi, toptrader_ls_ratio, taker_vol_ratio |
| OI+LS+Taker Live | `data_collector/data/bn_{oi,ls_ratio,taker_ratio}.parquet` | 3.702 | 2026-04-09 → 2026-05-05 | Cron-Polling, ~26 Tage |
| Klines+Taker | `data_collector/data/bn_klines_1h.parquet` | 52.614 | 2025-05-04 → 2026-05-05 | 1 Jahr, 6 Assets, taker_buy_vol |
| DXY Broad | `data_collector/data/dxy_broad_daily.parquet` | 5.097 | 2006 → 2026 | FRED DTWEXBGS |
| HL Funding | `data_collector/data/hl_funding_full.parquet` | 80.978 | 2023-11-14 → 2026-04-30 | 2.5 Jahre, 6 Assets |
| Preise 1h | `data_collector/data/prices_all_1h.parquet` | 120.007 | 2023-11-15 → 2026-04-30 | 6 Assets |
| Preise Research | `research/data/{ASSET}USDT_1h_full.parquet` | ~20.158 × 8 | 2023-11-15 → 2026-04-30 | 8 Assets |
| FGI | `data_collector/data/fear_greed.parquet` | 3.012 | — | Fear & Greed Index |
| Binance Funding 8h | `data_collector/data/bn_funding.parquet` | 1.704 | — | 6 Assets |

### ⚠️ WICHTIG: OI/Taker Datenlage
- Die **2-Jahres-Backfill-Daten** liegen in `data/bn_metrics_*.parquet` (17.593 Zeilen/Asset)
- Die **Live-Cron-Daten** in `data_collector/data/bn_{oi,ls_ratio,taker_ratio}.parquet` haben nur ~26 Tage
- Sweep V14 nutzte die **2-Jährigen** Backfill-Daten — Ergebnisse sind valide
- MEMORY.md behauptete früher "25 Tage" — das war FALSCH, betraf nur die Live-API

---

## Ergebnis-Dateien (verifiziert 2026-05-05)

| Datei | Inhalt | Status |
|-------|--------|--------|
| `cpcv_validated_20260504_153055.json` | 17 CPCV-validated Signale (Phase 1.1 Funding) | ✅ OK |
| `dsr_validated_20260504_153055.json` | 60 DSR-passed (vor CPCV-Filter) | ✅ OK |
| `sweep_4h_20260504_153055.json` | 60 IS-Ergebnisse Phase 1.1 | ✅ OK |
| `sweep_v14_20260504_215514.json` | 168 V14 IS-Ergebnisse (Run 1) | ✅ OK |
| `sweep_v14_20260504_215851.json` | 168 V14 IS-Ergebnisse (Run 2, final) | ✅ OK |
| `crosssec_validated_20260504_crosssec.json` | Cross-sec IS-Ergebnisse | ❌ TRUNCATED — kein schließendes `]` |
| `foundry_v13_iter1_20260504_193513.json` | 8 Foundry V13 Hypothesen | ✅ OK |
| `foundry_v13_iter1_20260504_201629.json` | Foundry Run 2 | ❌ PARSE_ERROR |
| `foundry_v13_iter1_20260504_202317.json` | 8 Foundry V13 Hypothesen | ✅ OK |

---

## Portfolio: Validierte Signale (5 total)

### Phase 1.1 — Funding Sweep (4h, CPCV-validated)

| # | Signal | PBO | OOS WR | OOS Return | IS Sharpe | Trades | Asset |
|---|--------|-----|--------|-----------|-----------|--------|-------|
| 1 | BTC mild_neg + bull200 | 0.13 | 86.7% | +31.9% | 9.05 | 176 | BTC |
| 2 | ETH mild_neg + bull200 | 0.13 | 86.7% | +26.8% | 6.75 | 168 | ETH |
| 3 | BTC slight_neg (no filter) | 0.20 | 80.0% | +25.1% | 5.53 | 238 | BTC |

Korrelationen: BTC↔ETH ρ=0.06, BTC-Varianten untereinander ρ=0.52-0.98

### Phase 1.3+1.4 — Cross-Sectional Funding (4h, CPCV-validated)

| # | Signal | PBO | OOS Return | Trades | Asset |
|---|--------|-----|-----------|--------|-------|
| 4 | BTC crosssec z<-1.0 + bull200 | 0.20 | +15.1% | 121 | BTC |

Korrelation zu abs. Funding: ρ=0.02 (unkorreliert!)

### Phase 1 → V14 — Extended Features (4h, CPCV-validated, 2yr Daten)

| # | Signal | PBO | OOS Return | IS Return | Trades | Asset |
|---|--------|-----|-----------|-----------|--------|-------|
| 5 | OI Surge SOL h48 sl5 (ΔOI>3%) | 0.33 | +66.6% | +101.2% | 32 | SOL |
| 6 | OI Surge SOL h24 sl5 (ΔOI>3%) | 0.33 | +68.9% | +66.7% | 41 | SOL |
| 7 | LS Ratio SOL >5 Short | 0.33 | +57.3% | +53.7% | 30 | SOL |

⚠️ OI Surge BTC h48 sl5: PBO=0.50 (medium), OOS=+68.2%
❌ OI Surge BTC h24 sl0: PBO=0.83 (overfit), OOS=-151%

### V14 Top-IS (nicht CPCV-validated, >20 trades)

| Signal | IS Return | Trades | WR | Sharpe |
|--------|-----------|--------|-----|--------|
| OI Surge SOL h48 sl5 t3.0 | +101.2% | 32 | 53.1% | 13.86 |
| LS SOL t5.0 h48 sl5 | +79.9% | 21 | 52.4% | 14.74 |
| OI Surge SOL h24 sl5 t3.0 | +66.7% | 41 | 56.1% | 11.05 |
| LS ETH t4.0 h48 sl5 | +63.5% | 42 | 45.2% | 7.94 |
| OI Surge BTC h48 sl5 t3.0 | +54.1% | 34 | 55.9% | 11.15 |
| Taker BTC t2.0 h24 sl5 | +34.7% | 73 | 53.4% | 5.26 |

---

## Edge Registry (4 Einträge, verifiziert 2026-05-05)

1. `SOL_mild_neg_funding` — **production** (Sharpe=1.8, OOS=+4.83%, 239 trades)
2. `SOL_mild_neg_funding_narrow` — **deprecated** (korreliert mit #1)
3. `btc_mild_neg_bull200_4h` — **validated** (Sharpe=9.05, PBO=0.13, OOS=+31.9%)
4. `eth_mild_neg_bull200_4h` — **validated** (Sharpe=6.75, PBO=0.13, OOS=+26.8%)

**FEHLT:** BTC crosssec, OI Surge SOL, LS Ratio SOL (noch nicht eingetragen)

---

## V2 Paper Engine (LIVE)

- **Equity:** 100.27€ (100€ Start, +0.27€ PnL)
- **Aktuell:** ETH LONG offen (Entry $2.363,41), BTC gerade geschlossen (+0.27€)
- **Signal Generator V2:** `executor/signal_generator_v2.py`
  - SOL: z∈[-0.5, 0) + bull200 → LONG
  - SOL: z<-0.5 + bull200 → LONG (extended)
  - BTC: mild_neg + bull200, OI Surge, LS Ratio Short, Taker Buy
  - ETH: mild_neg + bull200
  - Exit: 24h time-based, SL 4-5%, Trailing DISABLED
- **Data Feed V2:** `executor/data_feed_v2.py`
  - Funding: HL 1h, Binance 8h, Polling alle 5min
  - FGI, EMA200/EMA50, OI, LS Ratio, Taker Vol Ratio
- **Paper Engine V2:** `executor/paper_engine_v2.py`
  - Assets: BTC, ETH, SOL
  - Capital: 100€ TOTAL, Leverage: BTC 1.8x, ETH 1.5x, SOL 1.0x

---

## Phase-Status

| Phase | Status | Ergebnis |
|-------|--------|----------|
| 0 Foundation | ✅ COMPLETE | DSR, MC, Bonferroni, Korrelation, V2 Fix |
| 1 Infrastructure | ✅ COMPLETE | CPCV, BH-FDR, Edge Registry (464→466 Tests) |
| 1.1 Funding Sweep | ✅ COMPLETE | 60 Hyp → 17 DSR → 17 CPCV → BTC+ETH mild_neg |
| 1.2 Liquidation | ❌ DEFERRED | Nur 152 OI-Datenpunkte auf 4h, zu dünn |
| 1.3+1.4 Cross-Sec | ✅ COMPLETE | BTC crosssec z<-1.0, ρ=0.02 |
| V14 Extended | ✅ COMPLETE | 168 Hyp, OI Surge PBO=0.33, LS Ratio PBO=0.33 |
| Foundry V13 | ✅ BUILT+RUN | LLM → JSON-DSL → Sweep → DSR+CPCV Pipeline |
| V14 → 1.2 Pivot | ✅ COMPLETE | OI Surge ersetzt Liquidation (2yr Daten! =) |
| 2 Validation | 🔴 Offen | Prop-Firm, Steuern, Copy Trading |

---

## Cron-Jobs (aktiv)

| Name | Schedule | Zweck |
|------|----------|-------|
| v2-data-collector | :10 stündlich | Funding + FGI + OI/LS/Taker sammeln |
| engine-watchdog | :00 stündlich | V2 Engine überwachen |
| monitor-update | alle 4h | Dashboard aktualisieren |
| housekeeping | 09:00 Berlin | Accounting Check |
| foundry-v12 | DISABLED | War LLM-Exploration, ersetzt durch V13 |

---

## Known Bugs / Issues (2026-05-05)

1. ~~bn_klines Schema Mismatch~~ ✅ FIXED (fetch_historical calls compute_taker_ratio, collector merge handles schema diff)
2. crosssec_validated JSON truncated — Datei unvollständig, kein schließendes `]`
3. **foundry_v13 Run 2 JSON** — Parse Error
4. ~~Edge Registry~~ ✅ FIXED — 7 Einträge inkl. crosssec + V4
5. ~~V14 CPCV~~ Result-File fehlt noch
6. **.gitignore** — Data-Parquets sollten nicht committed werden (prüfen!)

---

## Offene TODOs

1. ~~Cross-sec + V4 Signale in Edge Registry~~ ✅ DONE
2. Crosssec_validated JSON reparieren oder re-run
3. ~~bn_klines Schema Fix~~ ✅ DONE
4. ~~Korrelations-Check V4 Signale~~ ✅ DONE (5 unkorreliert)
5. V14 CPCV als separates Result-File speichern
6. .gitignore für data-Parquets prüfen
7. Git commit für offene Änderungen
8. DXY als Confluence-Filter (nicht Entry — DEAD als Entry)
9. FGI als Confluence-Filter implementieren
10. Prop-Firm Vorbereitung
11. Gewerbeanmeldung (§15 EStG)

---

## Deep Research Archiv (9 Dokumente)

- DR1-4: `research/deep_research_{1-4}_*.md` — Funding, Quant, Stats, Alpha
- DR5: `research/deep_research_hyperliquid.txt` — HL Migration
- DR6: `research/deep_research_propfirm.txt` + `_full.txt` — Prop-Firm
- DR7: `research/deep_research_defi.txt` — DeFi Yield/Regime
- DR8: `research/deep_research_liquidations.txt` — Liquidation Data
- DR9: `research/deep_research_data_architecture.txt` — Datenquellen-Matrix
- Synthese: `research/deep_research_complete_summary.md`
- ROADMAP: `research/ROADMAP.md` — Master Plan 12 Monate
- Foundry V13: `research/deep_research_foundry_v13_part1.txt` + `part2.txt`

---

## Sweep V13b+c Ergebnisse (Legacy, 2026-05-03)

### V13b (8h Funding, 3 Assets)
- 912 Backtests, 216 profitable IS, **1 WF-passed**
- Champion: SOL z∈[-0.5, 0) 24h SL5% → R=70 OOS=+4.83%

### V13c (6 Assets, 8 Tiers)
- 4920 Backtests, 611 profitable IS, **0 WF-passed**
- LS/Taker BUG gefixt (Spaltennamen), aber nur 74 Datenpunkte auf 8h
- Nur SOL hat robusten Edge

### V13b Label-Bug
- `bear_z<-0.5` war eigentlich z∈[-0.5, 0) = mild negativ
- V13c hat korrekte z_low/z_high_ranges

### V1 Lessons (MACD = tot)
- Trailing Stop 2% zu eng (25% Win Rate)
- Entry oft spät im Trend
- RSI/BB/EMA NICHT als Bestätigung — 0 Alpha bewiesen
- 100€ = TOTAL, nicht pro Asset