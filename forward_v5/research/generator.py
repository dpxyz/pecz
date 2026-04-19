"""
Generator v0.2 – KI-gestützter Strategie-Generator

Liest Spec + (optional) Feedback von vorherigem FAIL.
Generiert Kandidaten im DSL-Format.
Nutzt Gemma4:31b über Ollama API.

v0.2: Verbesserter Prompt mit konkreten DSL-Beispielen, Exit-Regeln,
      Fokus auf Mean-Reversion, verhindert period=0 und Trend-Following.
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


def build_prompt(spec: dict, feedback: str = None, iteration: int = 1) -> str:
    """Build the generation prompt for the KI."""
    
    spec_str = yaml.dump(spec, default_flow_style=False)
    
    prompt = f"""Du bist ein Quant-Stratege. Generiere Strategie-Kandidaten basierend auf dieser Spec.

SPEC:
{spec_str}

REGELN:
1. Generiere genau {spec.get('evolution', {}).get('candidates_per_iteration', 3)} Kandidaten
2. Jeder Kandidat MUSS im DSL-Format sein (siehe unten)
3. Jeder Kandidat MUSS gegen die Spec-Kriterien konstruiert sein

KRITISCHE REGELN (VERLETZUNG = INVALID):
- NIEMALS period=0 oder period=1! Minimum ist period=2
- entry.condition MUSS ein konkreter DSL-Ausdruck sein, KEIN Freitext!
- entry.condition MUSS Indikatoren referenzieren, die unter indicators: gelistet sind
- Bevorzuge mean_reversion und breakout-Strategien – trend_following funktioniert schlecht auf 1h-Data
- Nutze IMMER exit-Regeln: take_profit_pct (1.5-3.0) und stop_loss_pct (1.5-3.0) und max_hold_bars (24-72)

DSL-AUSDRÜCKE FÜR CONDITIONS:
- Vergleich: INDICATOR OP VALUE (z.B. rsi_14 < 30)
- Logisch: AND, OR (z.B. rsi_14 < 30 AND close < ema_20)
- WICHTIG: Indikator-Name MUSS mit period-Nummer matchen!
  - Richtig: rsi_14 < 30 (wenn indicators: [{{"name": "RSI", "params": {{"period": 14}}}}])
  - Falsch: rsi < 30 (ohne Nummer)
  - Richtig: close < ema_20 (wenn indicators: [{{"name": "EMA", "params": {{"period": 20}}}}])
  - Richtig: close > bb_upper_20 (wenn indicators: [{{"name": "BB", "params": {{"period": 20, "std_dev": 2.0}}}}])

ERPROBTE STRATEGIE-MUSTER (bevorzuge diese):
1. RSI Mean Reversion: rsi_14 < 30 AND close < bb_lower_20 (entry) → rsi_14 > 70 (exit condition)
2. ZScore Reversion: zscore_50 < -2.0 AND close < bb_lower_20 → zscore_50 > 2.0
3. BB Bounce: close < bb_lower_20 AND rsi_14 < 35 → close > bb_mid_20
4. RSI + EMA Filter: rsi_14 < 30 AND close > ema_50 (trend filter) → rsi_14 > 65
5. ZScore + ATR Volatility: zscore_20 < -1.5 AND atr_14 > close * 0.02 → zscore_20 > 1.5

MEIDE: Reine Trend-Following (SMA/EMA Crossover) – generiert zu wenige Signale auf 1h-Data!

DSL-FORMAT (genau dieses JSON-Format, kein Markdown, keine Code-Blöcke):
{{
  "dsl_version": "0.1",
  "strategy": {{
    "name": "deskriptiver_name",
    "type": "mean_reversion|breakout|hybrid",
    "hypothesis": "Warum diese Strategie funktionieren sollte",
    "assets": ["BTCUSDT"],
    "timeframe": "1h",
    "indicators": [
      {{"name": "RSI", "params": {{"period": 14}}}},
      {{"name": "BB", "params": {{"period": 20, "std_dev": 2.0}}}}
    ],
    "entry": {{
      "condition": "rsi_14 < 30 AND close < bb_lower_20",
      "max_per_day": 3
    }},
    "exit": {{
      "take_profit_pct": 2.0,
      "stop_loss_pct": 1.5,
      "trailing_stop_pct": null,
      "max_hold_bars": 48
    }},
    "position_sizing": {{
      "method": "fixed_frac",
      "risk_per_trade_pct": 1.0
    }},
    "filters": []
  }}
}}

Gültige Indikatoren: SMA, EMA, RSI, BB, ATR, VWAP, MACD, ZSCORE
Gültige Zeitrahmen: 1h
Gültige Assets: BTCUSDT, ETHUSDT, SOLUSDT

AUSGABE: Nur ein JSON-Array mit den Kandidaten. Kein Text davor oder danach.
Beispiel: [{{"dsl_version": "0.1", "strategy": {{...}}}}, ...]"""

    if feedback:
        prompt += f"""

FEEDBACK VON VORHERIGEM VERSUCH (Iteration {iteration - 1}):
{feedback}

BERÜCKSICHTIGE dieses Feedback. Verbessere die Strategie basierend auf den FAIL-Gates.
Wenn "No trades generated": Nutze weniger restriktive Entry-Conditions oder Mean-Reversion.
Wenn G1_profitability FAIL: Erhöhe take_profit_pct oder wähle volatilere Entry-Bedingungen.
Wenn G2_risk FAIL: Reduziere stop_loss_pct oder kürze max_hold_bars.
"""

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
    
    print(f"[Generator] Iteration {iteration}: Requesting {spec.get('evolution', {}).get('candidates_per_iteration', 3)} candidates...")
    
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
    
    print(f"[Generator] {len(valid_candidates)}/{len(candidates)} Kandidaten DSL-valid")
    return valid_candidates


if __name__ == "__main__":
    spec_path = Path(__file__).parent / "spec.yaml"
    with open(spec_path) as f:
        spec = yaml.safe_load(f)
    
    candidates = generate_candidates(spec)
    print(f"\nGenerated {len(candidates)} valid candidates:")
    for c in candidates:
        print(f"  - {c['strategy']['name']} ({c['strategy']['type']})")