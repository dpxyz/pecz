"""
Strategy DSL v0.1 – Kleine Sprache für Strategie-Kandidaten

Die DSL definiert was eine gültige Strategie-Konfiguration ist.
KI generiert im DSL-Format → Evaluator prüft → Kein freier Code.

Format:
{
  "dsl_version": "0.1",
  "strategy": {
    "name": "string",
    "type": "mean_reversion" | "trend_following" | "breakout" | "hybrid",
    "hypothesis": "string",
    "assets": ["BTCUSDT", ...],          # max 3
    "timeframe": "1h" | "4h" | "15m",
    "indicators": [
      {
        "name": "SMA" | "EMA" | "RSI" | "BB" | "ATR" | "VWAP" | "MACD" | "ZSCORE",
        "params": { "period": int, ... }
      }
    ],
    "entry": {
      "condition": "string (DSL expression)",
      "max_per_day": int
    },
    "exit": {
      "take_profit_pct": float,
      "stop_loss_pct": float,
      "trailing_stop_pct": float | null,
      "max_hold_bars": int
    },
    "position_sizing": {
      "method": "fixed_frac" | "kelly" | "fixed_qty",
      "risk_per_trade_pct": float
    },
    "filters": [
      {
        "type": "time" | "volatility" | "volume" | "trend",
        "params": {}
      }
    ]
  }
}
"""

from dataclasses import dataclass, field
from typing import Optional
import json

# ── Allowed values ──
STRATEGY_TYPES = {"mean_reversion", "trend_following", "momentum", "breakout", "hybrid"}
INDICATOR_NAMES = {"SMA", "EMA", "RSI", "BB", "ATR", "VWAP", "MACD", "ZSCORE"}
VALID_TIMEFRAMES = {"15m", "1h", "4h"}
VALID_ASSETS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "XRPUSDT", "ADAUSDT"}
SIZING_METHODS = {"fixed_frac", "kelly", "fixed_qty"}
FILTER_TYPES = {"time", "volatility", "volume", "trend"}


@dataclass
class DSLError:
    path: str
    message: str


def validate_candidate(candidate: dict) -> tuple[bool, list[DSLError]]:
    """Validate a strategy candidate against DSL rules.
    Returns (is_valid, list_of_errors)."""
    errors = []
    
    # ── Top-level ──
    if candidate.get("dsl_version") != "0.1":
        errors.append(DSLError("dsl_version", f"Expected '0.1', got '{candidate.get('dsl_version')}'"))
    
    strategy = candidate.get("strategy", {})
    if not strategy:
        errors.append(DSLError("strategy", "Missing strategy object"))
        return False, errors
    
    # ── Name ──
    name = strategy.get("name", "")
    if not name or len(name) < 3:
        errors.append(DSLError("strategy.name", "Name must be at least 3 characters"))
    
    # ── Type ──
    stype = strategy.get("type", "")
    if stype not in STRATEGY_TYPES:
        errors.append(DSLError("strategy.type", f"Must be one of {STRATEGY_TYPES}, got '{stype}'"))
    
    # ── Assets ──
    assets = strategy.get("assets", [])
    if not assets:
        errors.append(DSLError("strategy.assets", "At least one asset required"))
    if len(assets) > 3:
        errors.append(DSLError("strategy.assets", f"Max 3 assets, got {len(assets)}"))
    for a in assets:
        if a not in VALID_ASSETS:
            errors.append(DSLError("strategy.assets", f"Invalid asset '{a}', must be one of {VALID_ASSETS}"))
    
    # ── Timeframe ──
    tf = strategy.get("timeframe", "")
    if tf not in VALID_TIMEFRAMES:
        errors.append(DSLError("strategy.timeframe", f"Must be one of {VALID_TIMEFRAMES}, got '{tf}'"))
    
    # ── Indicators ──
    indicators = strategy.get("indicators", [])
    if not indicators:
        errors.append(DSLError("strategy.indicators", "At least one indicator required"))
    for i, ind in enumerate(indicators):
        iname = ind.get("name", "")
        if iname not in INDICATOR_NAMES:
            errors.append(DSLError(f"strategy.indicators[{i}].name", f"Invalid indicator '{iname}'"))
        params = ind.get("params", {})
        period = params.get("period", 0)
        if period < 2 or period > 500:
            errors.append(DSLError(f"strategy.indicators[{i}].params.period", f"Period must be 2-500, got {period}"))
    
    # ── Entry ──
    entry = strategy.get("entry", {})
    if not entry.get("condition"):
        errors.append(DSLError("strategy.entry.condition", "Entry condition required"))
    max_per_day = entry.get("max_per_day", 99)
    if max_per_day < 1 or max_per_day > 24:
        errors.append(DSLError("strategy.entry.max_per_day", f"Must be 1-24, got {max_per_day}"))
    
    # ── Exit ──
    exit_cfg = strategy.get("exit", {})
    tp = exit_cfg.get("take_profit_pct", 0)
    sl = exit_cfg.get("stop_loss_pct", 0)
    trailing = exit_cfg.get("trailing_stop_pct", None)
    # TP can be 0 if trailing_stop_pct is set (trend strategies)
    if tp <= 0 and not trailing:
        errors.append(DSLError("strategy.exit.take_profit_pct", f"Must be >0 or set trailing_stop_pct, got tp={tp}"))
    elif tp > 50:
        errors.append(DSLError("strategy.exit.take_profit_pct", f"Must be <=50%, got {tp}"))
    if sl <= 0 or sl > 50:
        errors.append(DSLError("strategy.exit.stop_loss_pct", f"Must be 0-50%, got {sl}"))
    max_hold = exit_cfg.get("max_hold_bars", 0)
    if max_hold < 1 or max_hold > 1000:
        errors.append(DSLError("strategy.exit.max_hold_bars", f"Must be 1-1000, got {max_hold}"))
    
    # ── Position Sizing ──
    sizing = strategy.get("position_sizing", {})
    method = sizing.get("method", "")
    if method not in SIZING_METHODS:
        errors.append(DSLError("strategy.position_sizing.method", f"Must be one of {SIZING_METHODS}"))
    risk = sizing.get("risk_per_trade_pct", 0)
    if risk <= 0 or risk > 10:
        errors.append(DSLError("strategy.position_sizing.risk_per_trade_pct", f"Must be 0-10%, got {risk}"))
    
    # ── Filters ──
    filters = strategy.get("filters", [])
    for i, f in enumerate(filters):
        ftype = f.get("type", "")
        if ftype not in FILTER_TYPES:
            errors.append(DSLError(f"strategy.filters[{i}].type", f"Invalid filter type '{ftype}'"))
    
    return len(errors) == 0, errors


def candidate_to_prompt(candidate: dict) -> str:
    """Convert a validated candidate to a compact prompt string for the KI."""
    return json.dumps(candidate, indent=2)


def errors_to_feedback(errors: list[DSLError]) -> str:
    """Convert DSL errors to human-readable feedback for the KI."""
    lines = ["DSL-Validierung fehlgeschlagen:"]
    for e in errors:
        lines.append(f"  - {e.path}: {e.message}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Example valid candidate
    example = {
        "dsl_version": "0.1",
        "strategy": {
            "name": "mean_reversion_v2",
            "type": "mean_reversion",
            "hypothesis": "Extreme Z-Score moves revert to mean",
            "assets": ["BTCUSDT"],
            "timeframe": "1h",
            "indicators": [
                {"name": "SMA", "params": {"period": 60}},
                {"name": "ZSCORE", "params": {"period": 50}}
            ],
            "entry": {
                "condition": "zscore < -2.5 AND close < SMA_60",
                "max_per_day": 3
            },
            "exit": {
                "take_profit_pct": 1.5,
                "stop_loss_pct": 2.0,
                "trailing_stop_pct": None,
                "max_hold_bars": 48
            },
            "position_sizing": {
                "method": "fixed_frac",
                "risk_per_trade_pct": 1.0
            },
            "filters": [
                {"type": "volatility", "params": {"max_atr_multiplier": 2.0}}
            ]
        }
    }
    
    valid, errs = validate_candidate(example)
    print(f"Valid: {valid}")
    if errs:
        for e in errs:
            print(f"  {e.path}: {e.message}")
    else:
        print("✅ Example candidate is valid")