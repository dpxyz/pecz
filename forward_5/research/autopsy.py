#!/usr/bin/env python3
"""
Autopsie-Modul V2 — Tiefe Analyse WARUM ein WF-Kandidat fiel.

Analysen:
1. Exit-Reason-Analyse — SL dominiert? Trail kommt nie? → Exit-Optimierung
2. Window-Analyse — welche WF-Window profitabel, Pattern erkennen
3. Asset-Analyse — Stark/Schwach-Assets, Major vs Alt
4. Regime-Analyse — Trend-Assets gut, Range-Assets schlecht → Regime-Filter
5. Trade-Density-Analyse — Zu viele/wenig Trades → Entry anpassen
6. DD-Analyse — Hoher DD bei niedrigem Return → SL-Problem

Jede Analyse generiert gezielte Mutationen (entry_modifier, exit_modifier, suggestion).
"""

import json
import re
from typing import Optional


def classify_strategy_type(entry: str) -> str:
    """Classify strategy type from entry condition.
    Kept in sync with run_evolution_v8.py classify_strategy_type.
    """
    e = entry.lower()
    if 'bb_lower' in e or 'zscore' in e:
        if 'volume' in e:
            return 'VOL'
        return 'MR'
    if 'rsi' in e and ('close <' in e or '<' in e):
        if 'volume' in e:
            return 'VOL'
        return 'MR'
    if 'bb_width' in e:
        return 'REGIME'
    if 'atr_' in e and 'bb' not in e and 'rsi' not in e:
        return 'REGIME'
    if 'adx' in e or 'ema_slope' in e:
        return 'TREND'
    if 'close > ema_' in e and 'close > ema_200' in e:
        return 'TREND'
    if 'roc_' in e or 'macd_hist' in e or ('bb_upper' in e and 'close >' in e):
        return 'MOM'
    if 'stoch' in e or 'williams' in e:
        return 'MR'
    return 'MR'


def autopsie(candidate: dict, wf_result: dict) -> dict:
    """
    Tiefe Autopsie eines WF-Kandidaten.

    Args:
        candidate: Strategie mit IS-Ergebnis (enthält exit_reasons, per_asset_returns)
        wf_result: WF-Ergebnis von run_wf_on_candidate()

    Returns:
        {learnings, mutations, priority, candidate_name, ...}
    """
    learnings = []
    mutations = []
    entry = candidate.get("entry_condition", candidate.get("entry", ""))
    exit_config = candidate.get("exit_config", {})
    is_result = candidate  # IS-backtest-Felder sind direkt im Kandidaten

    # =========================================================================
    # 1. EXIT-REASON-ANALYSE (NEU - die wichtigste Analyse)
    # =========================================================================
    exit_reasons = is_result.get("exit_reasons", {})

    if exit_reasons:
        total_trades = sum(d["count"] for d in exit_reasons.values())
        sl_count = exit_reasons.get("stop_loss", {}).get("count", 0)
        trail_count = exit_reasons.get("trailing_stop", {}).get("count", 0)
        max_hold_count = exit_reasons.get("max_hold", {}).get("count", 0)
        signal_count = exit_reasons.get("signal_exit", {}).get("count", 0)
        tp_count = exit_reasons.get("take_profit", {}).get("count", 0)

        sl_pct = sl_count / total_trades if total_trades > 0 else 0
        trail_pct = trail_count / total_trades if total_trades > 0 else 0
        max_hold_pct = max_hold_count / total_trades if total_trades > 0 else 0

        # --- SL dominiert (>50% der Exits) ---
        if sl_pct > 0.5:
            sl_avg_pnl = exit_reasons.get("stop_loss", {}).get("avg_pnl", 0)
            learnings.append(
                f"SL dominiert ({sl_pct:.0%} der Exits, avg PnL={sl_avg_pnl:+.1f}%) — "
                f"Entry timing schlecht ODER SL zu eng"
            )
            # Mutation 1: SL weiter + Trail weiter (mehr Raum)
            mutations.append({
                "type": "exit_widen",
                "msg": f"SL {sl_pct:.0%} → weiterer SL +1%, Trail +0.5%",
                "exit_modifier": {
                    "trailing_stop_pct": exit_config.get("trailing_stop_pct", 2.0) + 0.5,
                    "stop_loss_pct": exit_config.get("stop_loss_pct", 3.0) + 1.0,
                    "max_hold_bars": exit_config.get("max_hold_bars", 24),
                },
            })
            # Mutation 2: Kürzerer Max-Hold + engerer Trail (schneller raus)
            mutations.append({
                "type": "exit_quick",
                "msg": f"SL {sl_pct:.0%} → kürzerer Max-Hold, engerer Trail für Quick-Profits",
                "exit_modifier": {
                    "trailing_stop_pct": max(1.0, exit_config.get("trailing_stop_pct", 2.0) - 0.5),
                    "stop_loss_pct": exit_config.get("stop_loss_pct", 3.0),
                    "max_hold_bars": max(8, exit_config.get("max_hold_bars", 24) - 8),
                },
            })

        # --- Trail kommt nie (<5% der Exits) ---
        if trail_pct < 0.05 and sl_pct > 0.2:
            learnings.append(
                f"Trail selten ({trail_pct:.0%}) aber SL aktiv ({sl_pct:.0%}) — "
                f"Trail zu eng oder Trades drehen vor Trail-Trigger"
            )
            mutations.append({
                "type": "trail_widen",
                "msg": "Trail weiter +0.5% damit Gewinne atmen können",
                "exit_modifier": {
                    "trailing_stop_pct": exit_config.get("trailing_stop_pct", 2.0) + 0.5,
                    "stop_loss_pct": exit_config.get("stop_loss_pct", 3.0),
                    "max_hold_bars": exit_config.get("max_hold_bars", 24),
                },
            })

        # --- Max-Hold dominiert (>30%) ---
        if max_hold_pct > 0.3:
            learnings.append(
                f"Max-Hold dominiert ({max_hold_pct:.0%}) — Positionen verweilen zu lang, kein Exit-Signal"
            )
            mutations.append({
                "type": "shorter_hold",
                "msg": "Max-Hold reduzieren, damit Positionen nicht im Nirvana hängen",
                "exit_modifier": {
                    "trailing_stop_pct": exit_config.get("trailing_stop_pct", 2.0),
                    "stop_loss_pct": exit_config.get("stop_loss_pct", 3.0),
                    "max_hold_bars": max(6, exit_config.get("max_hold_bars", 24) - 6),
                },
            })

        # --- Trail dominiert (>40%) mit positivem avg PnL → gutes Zeichen ---
        if trail_pct > 0.4:
            trail_avg = exit_reasons.get("trailing_stop", {}).get("avg_pnl", 0)
            if trail_avg > 0:
                learnings.append(
                    f"Trail dominiert ({trail_pct:.0%}, avg PnL={trail_avg:+.1f}%) — "
                    f"Gewinne werden getrailt, Strategie hat Trend-Komponente"
                )

    # =========================================================================
    # 2. WINDOW-ANALYSE
    # =========================================================================
    assets_data = wf_result.get("assets", {})
    window_returns = []
    window_details = []  # [(asset, window, return, trades, dd)]

    for asset, data in assets_data.items():
        if isinstance(data, dict) and "windows" in data:
            for w in data["windows"]:
                ret = w.get("net_return", 0)
                window_returns.append(ret)
                window_details.append({
                    "asset": asset,
                    "window": w.get("window", 0),
                    "return": ret,
                    "trades": w.get("trade_count", 0),
                    "dd": w.get("max_drawdown", 0),
                })

    n_profitable = sum(1 for r in window_returns if r > 0)
    n_total = len(window_returns)

    if n_total > 0:
        profitable_pct = n_profitable / n_total

        if profitable_pct >= 0.5:
            learnings.append(
                f"Nah dran: {n_profitable}/{n_total} Windows profitabel ({profitable_pct:.0%})"
            )
            mutations.append({
                "type": "fine_tune",
                "msg": "Feintuning statt Umbau — Entry funktioniert teilweise",
                "entry_modifier": None,
                "suggestion": "Parameter-Sweep mit engem Grid um aktuelle Werte",
            })
        elif profitable_pct >= 0.3:
            learnings.append(
                f"Teilprofitabel: {n_profitable}/{n_total} ({profitable_pct:.0%})"
            )
        else:
            learnings.append(
                f"Schlecht: {n_profitable}/{n_total} Windows profitabel ({profitable_pct:.0%})"
            )

        # Pattern-Erkennung: Sind bestimmte Windows konsistent schlecht?
        if n_total >= 10:
            # Sortiere nach Window-Nummer
            by_window = {}
            for wd in window_details:
                by_window.setdefault(wd["window"], []).append(wd["return"])

            # Windows die über alle Assets negativ sind
            always_bad_windows = []
            sometimes_good_windows = []
            for wnum, rets in sorted(by_window.items()):
                if all(r <= 0 for r in rets):
                    always_bad_windows.append(wnum)
                elif any(r > 0 for r in rets):
                    sometimes_good_windows.append(wnum)

            if always_bad_windows and len(always_bad_windows) <= 3:
                learnings.append(
                    f"Immer schlecht: Window {always_bad_windows} — "
                    f"mögliche strukturelle Schwäche in diesen Marktphasen"
                )

    # =========================================================================
    # 3. ASSET-ANALYSE
    # =========================================================================
    per_asset_returns = {}
    for asset, data in assets_data.items():
        if isinstance(data, dict) and "avg_oos_return" in data:
            per_asset_returns[asset] = data["avg_oos_return"]

    # Fallback: nutze IS per_asset_returns wenn WF-Assets fehlen
    if not per_asset_returns:
        is_per_asset = is_result.get("per_asset_returns", {})
        for asset, periods in is_per_asset.items():
            if isinstance(periods, dict):
                per_asset_returns[asset] = sum(periods.values()) / len(periods) if periods else 0

    if per_asset_returns:
        strong = sorted([a for a, r in per_asset_returns.items() if r > 0])
        weak = sorted([a for a, r in per_asset_returns.items() if r <= 0])

        if strong and weak:
            learnings.append(f"Asset-Split: stark={strong}, schwach={weak}")
            if len(strong) <= 3:
                mutations.append({
                    "type": "asset_filter",
                    "msg": f"Nur auf {strong} traden — evtl. EMA-Filter enger für Alts",
                    "entry_modifier": entry + " AND close > ema_200" if "ema_200" not in entry else (entry + " AND close > ema_50" if "ema_50" not in entry else entry),
                    "exit_modifier": None,
                })

        # Major vs Alt Pattern
        majors = ["BTC", "ETH", "SOL"]
        major_returns = [per_asset_returns.get(a, 0) for a in majors if a in per_asset_returns]
        alt_returns = [per_asset_returns.get(a, 0) for a in per_asset_returns if a not in majors]

        if major_returns and alt_returns:
            avg_major = sum(major_returns) / len(major_returns)
            avg_alt = sum(alt_returns) / len(alt_returns)

            if avg_major > 0 and avg_alt < 0:
                learnings.append("Profitabel in Trend-Assets (BTC/ETH/SOL), verlustreich in Range-Assets")
                mutations.append({
                    "type": "add_regime_filter",
                    "msg": "Füge adx_14 > 20 als Entry-Filter hinzu",
                    "entry_modifier": _add_regime_filter(entry, "adx_14 > 20"),
                })
            elif avg_major < 0 and avg_alt > 0:
                learnings.append("Profitabel in Alt-Coins — Mean Reversion besser in choppy Märkten")
                mutations.append({
                    "type": "add_bb_width_filter",
                    "msg": "Füge bb_width_20 < 0.05 als Volatility-Deckel hinzu",
                    "entry_modifier": _add_bb_width_filter(entry, 0.05),
                })

    # =========================================================================
    # 4. REGIME-ANALYSE (heuristic basierend auf Asset-Korrelation)
    # =========================================================================
    # Wir können nicht direkt Trend/Range erkennen, aber wir können
    # aus der Asset-Korrelation Rückschlüsse ziehen:
    # - MR-Strategien: gut in volatilen Märkten (DOGE, ADA)
    # - Trend-Strategien: gut in Trend-Märkten (BTC, ETH)
    stype = candidate.get('strategy_type', classify_strategy_type(entry))

    # Cross-Check: Strategy-Typ vs Asset-Performance
    if per_asset_returns and stype in ["TREND", "MOM"]:
        # Trend/Momentum sollte auf BTC/ETH besser sein
        btc_eth_avg = (per_asset_returns.get("BTC", 0) + per_asset_returns.get("ETH", 0)) / 2
        doge_ada_avg = (per_asset_returns.get("DOGE", 0) + per_asset_returns.get("ADA", 0)) / 2
        if btc_eth_avg < 0 and doge_ada_avg > 0:
            learnings.append(
                "Trend-Strategie funktioniert paradox auf Alts besser — "
                "evtl. ist der Trend-Filter (EMA/ADX) auf Majors zu spät"
            )
            mutations.append({
                "type": "faster_trend",
                "msg": "Kürzere EMAs (ema_20 statt ema_50) für frühere Entries",
                "entry_modifier": _shift_ema_faster(entry),
            })

    if per_asset_returns and stype in ["MR", "VOL"]:
        # MR sollte auf volatilen Assets besser sein
        volatile = [per_asset_returns.get("DOGE", 0), per_asset_returns.get("ADA", 0)]
        stable = [per_asset_returns.get("BTC", 0), per_asset_returns.get("ETH", 0)]
        if any(v > 0 for v in volatile) and all(s <= 0 for s in stable):
            learnings.append(
                "MR funktioniert nur auf volatilen Alts — auf BTC/ETH zu selten oversold"
            )
            mutations.append({
                "type": "wider_mr",
                "msg": "BB/RSI Thresholds weiter (z.B. rsi < 35 statt 30) für mehr Entries",
                "entry_modifier": _loosen_entry(entry),
            })

    # =========================================================================
    # 5. TRADE-DENSITY-ANALYSE
    # =========================================================================
    avg_trades_wf = wf_result.get("avg_trades", 0)
    if avg_trades_wf == 0:
        # Fallback aus IS
        avg_trades_wf = is_result.get("min_trades", 0)

    if avg_trades_wf < 3:
        learnings.append(f"Zu wenige Trades ({avg_trades_wf:.1f}/Window) — Entry zu restriktiv")
        mutations.append({
            "type": "loosen_entry",
            "msg": "Entry-Bedingung lockern (weniger Filter oder Thresholds anpassen)",
            "entry_modifier": _loosen_entry(entry),
        })
    elif avg_trades_wf > 50:
        learnings.append(f"Zu viele Trades ({avg_trades_wf:.1f}/Window) — Entry zu lose, Whipsaw-Risiko")
        mutations.append({
            "type": "tighten_entry",
            "msg": "Entry-Bedingung verschärfen (zusätzlicher Filter oder Thresholds enger)",
            "entry_modifier": _tighten_entry(entry),
        })

    # =========================================================================
    # 6. DD-ANALYSE
    # =========================================================================
    avg_dd = is_result.get("avg_dd", 0)
    avg_return = is_result.get("avg_return", 0)

    if avg_dd > 0 and avg_return < 0:
        dd_return_ratio = abs(avg_dd / avg_return) if avg_return != 0 else 999
        if dd_return_ratio > 3:
            learnings.append(
                f"DD/Return-Ratio={dd_return_ratio:.1f} — Risiko unverhältnismäßig hoch"
            )
            if not any(m["type"] == "exit_widen" for m in mutations):
                mutations.append({
                    "type": "exit_widen",
                    "msg": "Weiterer SL +1.0% um DD zu reduzieren",
                    "exit_modifier": {
                        "trailing_stop_pct": exit_config.get("trailing_stop_pct", 2.0),
                        "stop_loss_pct": exit_config.get("stop_loss_pct", 3.0) + 1.0,
                        "max_hold_bars": exit_config.get("max_hold_bars", 24),
                    },
                })

    # =========================================================================
    # PRIORITÄT
    # =========================================================================
    if n_total > 0 and profitable_pct >= 0.5:
        priority = "high"
    elif n_total > 0 and profitable_pct >= 0.3:
        priority = "medium"
    elif per_asset_returns and any(r > 0 for r in per_asset_returns.values()):
        priority = "medium"
    else:
        priority = "low"

    return {
        "learnings": learnings,
        "mutations": mutations,
        "priority": priority,
        "candidate_name": candidate.get("name", "?"),
        "n_profitable_windows": f"{n_profitable}/{n_total}",
        "n_profitable_assets": f"{sum(1 for r in per_asset_returns.values() if r > 0)}/{len(per_asset_returns)}",
        "exit_reasons_summary": {r: f"{d['count']} ({d['count']/sum(x['count'] for x in exit_reasons.values()):.0%})"
                                 for r, d in exit_reasons.items()} if exit_reasons else {},
    }


# ============================================================================
# HELPER: Entry-Modifier
# ============================================================================

def _add_bb_width_filter(entry: str, threshold: float) -> Optional[str]:
    if "bb_width" in entry:
        return None
    return f"{entry} AND bb_width_20 < {threshold}"


def _add_regime_filter(entry: str, condition: str) -> Optional[str]:
    if any(kw in entry.lower() for kw in ["adx", condition.split()[0]]):
        return None
    return f"{entry} AND {condition}"


def _loosen_entry(entry: str) -> Optional[str]:
    """Lockere Entry-Bedingung: RSI < 30 → 35, BB weiter, letzter Filter entfernen."""
    modified = entry
    # RSI < X → X+5
    modified = re.sub(r'rsi_(\d+) < (\d+)', lambda m: f'rsi_{m.group(1)} < {int(m.group(2)) + 5}', modified)
    # Stochastic < X → X+5
    modified = re.sub(r'stoch_k_(\d+) < (\d+)', lambda m: f'stoch_k_{m.group(1)} < {int(m.group(2)) + 5}', modified)
    # Williams < X → X+5 (more negative = more oversold, but we loosen)
    modified = re.sub(r'williams_r_(\d+) < -(\d+)', lambda m: f'williams_r_{m.group(1)} < -{max(50, int(m.group(2)) - 5)}', modified)
    # ZScore < -2 → -1.5
    modified = re.sub(r'zscore_\d+ < -2\.0', lambda m: m.group().replace('-2.0', '-1.5'), modified)
    if modified != entry:
        return modified
    # Letzter Filter entfernen
    parts = modified.split(" AND ")
    if len(parts) > 2:
        return " AND ".join(parts[:-1])
    return None


def _tighten_entry(entry: str) -> Optional[str]:
    """Verschärfe Entry-Bedingung."""
    if "volume" not in entry.lower():
        return f"{entry} AND volume > volume_sma_20"
    if "adx" not in entry.lower():
        return f"{entry} AND adx_14 > 20"
    return None


def _shift_ema_faster(entry: str) -> Optional[str]:
    """Ersetze langsame EMAs durch schnellere."""
    modified = entry
    modified = modified.replace("ema_200", "ema_100")
    modified = modified.replace("ema_100", "ema_50")
    if modified != entry:
        return modified
    return None


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        hof_file = sys.argv[1]
        with open(hof_file) as f:
            data = json.load(f)

        hof = data.get("hof", data.get("hall_of_fame", []))
        for entry in hof[:3]:
            print(f"\n{'='*60}")
            print(f"AUTOPSIE: {entry.get('name', '?')}")
            print(f"Entry: {entry.get('entry_condition', entry.get('entry', ''))}")

            # Re-run WF to get detailed results
            from walk_forward_gate import run_wf_on_candidate
            wf = run_wf_on_candidate(
                name=entry.get("name", "?"),
                entry=entry.get("entry_condition", entry.get("entry", "")),
                exit_config=entry.get("exit_config", {}),
            )

            result = autopsie(entry, wf)

            print(f"\n  Priority: {result['priority']}")
            print(f"  Profitable: {result['n_profitable_windows']} windows, {result['n_profitable_assets']} assets")
            if result.get('exit_reasons_summary'):
                print(f"  Exit reasons: {result['exit_reasons_summary']}")
            for l in result["learnings"]:
                print(f"  📝 {l}")
            for m in result["mutations"]:
                print(f"  🔀 {m['type']}: {m['msg']}")
                if m.get("entry_modifier"):
                    print(f"     → entry: {m['entry_modifier']}")
                if m.get("exit_modifier"):
                    print(f"     → exit: {json.dumps(m['exit_modifier'])}")
    else:
        print("Usage: python autopsy.py <hof_file>")