"""
Generator v0.3 – Multi-Regime Strategie-Generator

v0.3: Erweitert auf Trend-Following, Momentum, Breakout und Hybrid-Strategien.
      Basiert auf Validierungserkenntnissen: Mean-Reversion funktioniert nur in
      bestimmten Regimen (Bärenmarkt-Bottom, hohe Volatilität). Brauchen
      Strategien für Trend-Phasen (Bull-Markt, Range).

Nutzt Gemma4:31b über Ollama API.
"""

import json
import os
import re
import yaml
from datetime import datetime
from pathlib import Path
from strategy_dsl import validate_candidate, errors_to_feedback

API_URL = os.environ.get("OLLAMA_API_URL", "http://172.17.0.1:32769/v1/chat/completions")
API_KEY = os.environ.get("OLLAMA_API_KEY", "ollama-cloud")
MODEL = os.environ.get("GENERATOR_MODEL", "gemma4:31b-cloud")


# ── Validierungserkenntnisse (v0.3) ──
# Mean-Reversion (RSI<30, ZScore<-2):
#   - BTC 2024H1: +2.1% PF 1.46 ✅ (Bärenmarkt-Bottom)
#   - BTC 2023: -6.8% ❌ (Trend-Phase, Mean-Rev verliert)
#   - ETH: Konstant negativ ❌ (Momentum-Asset)
#   - SOL 2023: +6.6% ✅ (hohe Volatilität)
# 
# Fazit: Brauchen Trend-Following + Momentum für Bull-Phasen + Range-Phasen
# Strategie-Typen die funktionieren sollten:
#   1. Trend-Following: EMA-Crossover, Momentum (MACD, ADX)
#   2. Breakout: BB-Squeeze + Expansion, Donchian Channel
#   3. Hybrid: Regime-Adaptive (Trend-Filter + Entry-Art)


def build_prompt(spec: dict, feedback: str = None, iteration: int = 1) -> str:
    """Build the generation prompt for the KI."""
    
    spec_str = yaml.dump(spec, default_flow_style=False)
    n_candidates = spec.get('evolution', {}).get('candidates_per_iteration', 3)
    
    prompt = f"""Du bist ein Quant-Stratege für Crypto-Perps auf Hyperliquid (0.01% Maker-Fees, 100€ Startkapital).

SPEC:
{spec_str}

VALIDIERUNGS-ERGEBNISSE (aus echtem Backtest über 2+ Jahre):
- Mean-Reversion (RSI<30 AND Close>EMA100) funktioniert NUR in bestimmten Regimen
- BTC 2024H1: +2.1% PF 1.46 ✅ — aber BTC 2023: -6.8% ❌ (Bärenmarkt-Trend)
- ETH: Konstant negativ ❌ — Momentum-Asset, mean-reversion funktioniert nicht
- SOL 2023: +6.6% ✅ — hohe Volatilität begünstigt Mean-Reversion
- Walk-Forward: Nur 1-2/5 Fenster profitabel für Mean-Rev → zu schwankend

AUFGABE: Generiere {n_candidates} Strategie-Kandidaten die ROBUST über verschiedene Markt-Phasen funktionieren.

STRATEGIE-TYPEN (bevorzuge diese, MIX ist wichtig!):

1. **TREND-FOLLOWING** (funktionaliert in Bull-Märkten):
   - EMA-Crossover: EMA_12 > EMA_50 (Golden Cross)
   - MACD-Histogramm: macd_hist > 0 AND macd_line > signal_line
   - Pullback-in-Trend: close > ema_50 AND rsi_14 BETWEEN 40 AND 60
   - WICHTIG: Nutze trailing_stop_pct statt take_profit_pct für Trend-Riding!

2. **MOMENTUM** (funktioniert in starken Trends):
   - Breakout: close > bb_upper_20 AND atr_14 > atr_14_sma_20 (Volatility-Explosion)
   - RSI-Momentum: rsi_14 > 60 AND close > ema_20 (starker Aufwärts-Momentum)
   - Volume-Spike: close > sma_20 AND volume > volume_sma_20 * 1.5

3. **MEAN-REVERSION** (nur mit Regime-Filter!):
   - RSI_BB_Filtered: rsi_14 < 30 AND close < bb_lower_20 AND close > ema_100 (Trend-Filter)
   - ZScore mit ATR-Filter: zscore_20 < -2.0 AND atr_14 > atr_14_sma_20 * 0.8

4. **HYBRID / REGIME-ADAPTIVE**:
   - Trend-Pullback: ema_50 > ema_200 (Uptrend) AND rsi_14 < 35 (Pullback)
   - Volatility-Breakout: bb_width_20 < bb_width_20_sma_50 (Squeeze) → close > bb_upper_20 (Breakout)

KRITISCHE REGELN (VERLETZUNG = INVALID):
- NIEMALS period=0 oder period=1! Minimum ist period=2
- entry.condition MUSS ein konkreter DSL-Ausdruck sein (kein Freitext!)
- Indikator-Name MUSS mit period-Nummer matchen (rsi_14, ema_50, bb_upper_20 etc.)
- IMMER exit-Regeln: take_profit_pct ODER trailing_stop_pct + stop_loss_pct + max_hold_bars
- Trend-Strategien: Nutze trailing_stop_pct (1.5-3.0) statt take_profit_pct (gewinne laufen lassen!)
- Mean-Rev-Strategien: Nutze take_profit_pct (1.5-2.5) + stop_loss_pct (1.5-3.0)
- JEDER Kandidat MUSS mindestens einen Trend- oder Momentum-Indikator haben (EMA>50, MACD, ADX)

GÜLTIGE INDIKATOREN:
- SMA(period), EMA(period), RSI(period), BB(period, std_dev), ATR(period)
- MACD(fast, slow, signal), ZSCORE(period)
- VWAP (kein period), ADX(period)
- Sonder: bb_upper_N, bb_lower_N, bb_mid_N, bb_width_N, macd_line, macd_signal, macd_hist

GÜLTIGE CONDITION-OPERATOREN:
- <, >, <=, >=, AND, OR, BETWEEN (z.B. rsi_14 BETWEEN 40 AND 60)
- Arithmetik: close * 1.02, atr_14 * 0.8, volume_sma_20 * 1.5

DSL-FORMAT (genau dieses JSON, kein Markdown, keine Code-Blöcke):
{{
  "dsl_version": "0.1",
  "strategy": {{
    "name": "deskriptiver_name",
    "type": "trend_following|momentum|mean_reversion|breakout|hybrid",
    "hypothesis": "Warum diese Strategie über verschiedene Markt-Phasen robust ist",
    "assets": ["BTCUSDT"],
    "timeframe": "1h",
    "indicators": [
      {{"name": "EMA", "params": {{"period": 50}}}},
      {{"name": "RSI", "params": {{"period": 14}}}}
    ],
    "entry": {{
      "condition": "ema_12 > ema_50 AND rsi_14 > 50",
      "max_per_day": 3
    }},
    "exit": {{
      "trailing_stop_pct": 2.0,
      "stop_loss_pct": 2.0,
      "max_hold_bars": 48
    }},
    "position_sizing": {{
      "method": "fixed_frac",
      "risk_per_trade_pct": 1.0
    }},
    "filters": []
  }}
}}

AUSGABE: Nur ein JSON-Array. Kein Text davor oder danach.
Beispiel: [{{"dsl_version": "0.1", "strategy": {{...}}}}, ...]"""

    if feedback:
        prompt += f"""

FEEDBACK VON VORHERIGEM VERSUCH (Iteration {iteration - 1}):
{feedback}

BERÜCKSICHTIGE dieses Feedback. Wenn Mean-Reversion FAIL:
→ Versuche Trend-Following oder Momentum!
Wenn "No trades generated":
→ Nutze weniger restriktive Entry-Conditions.
Wenn G1_profitability FAIL:
→ Erhöhe trailing_stop oder nutze Trend-Riding statt fester TP.
Wenn G2_risk FAIL (DD zu hoch):
→ Nutze engeren stop_loss oder kürze max_hold_bars."""

    return prompt


def call_llm(prompt: str) -> str:
    """Call the LLM via OpenAI-compatible API."""
    import urllib.request
    
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 4096
    }).encode()
    
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
    )
    
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        # Gemma4 wraps JSON in code blocks – extract it
        json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', content, re.DOTALL)
        if json_match:
            return json_match.group(1)
        
        # Try raw JSON
        if content.strip().startswith('['):
            return content.strip()
        
        # Last resort: find array in text
        bracket_match = re.search(r'\[.*\]', content, re.DOTALL)
        if bracket_match:
            return bracket_match.group(0)
        
        raise ValueError(f"Could not extract JSON from LLM response: {content[:200]}")


def generate_candidates(spec: dict, feedback: str = None, iteration: int = 1) -> list[dict]:
    """Generate and validate strategy candidates."""
    prompt = build_prompt(spec, feedback, iteration)
    
    print(f"[Generator v0.3] Iteration {iteration}: Requesting {spec.get('evolution', {}).get('candidates_per_iteration', 3)} candidates...")
    
    raw = call_llm(prompt)
    candidates = json.loads(raw)
    
    # Validate each candidate
    valid_candidates = []
    for i, c in enumerate(candidates):
        is_valid, errors = validate_candidate(c)
        if is_valid:
            valid_candidates.append(c)
            print(f"  ✅ Kandidat {i+1} '{c['strategy']['name']}' – DSL valid")
        else:
            print(f"  ❌ Kandidat {i+1} – DSL invalid:")
            for e in errors:
                print(f"      {e.path}: {e.message}")
    
    print(f"[Generator v0.3] {len(valid_candidates)}/{len(candidates)} Kandidaten DSL-valid")
    return valid_candidates


if __name__ == "__main__":
    spec_path = Path(__file__).parent / "spec.yaml"
    with open(spec_path) as f:
        spec = yaml.safe_load(f)
    
    candidates = generate_candidates(spec)
    print(f"\nGenerated {len(candidates)} valid candidates:")
    for c in candidates:
        print(f"  - {c['strategy']['name']} ({c['strategy']['type']})")