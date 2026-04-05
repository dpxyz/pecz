#!/usr/bin/env python3
"""
KI Meta-Analyst — Ollama Cloud / Kimi 2.5

Analysiert fertige Scorecards und generiert strukturierte Meta-Analysen.
Keine Neuberechnungen — nur Bewertung vorliegender Ergebnisse.

Usage:
    python meta_analyst.py --scorecard scorecards/demo_scorecard_*.json
    python meta_analyst.py --scorecard scorecards/demo_scorecard_*.json --output meta_analysis_result.json

Environment:
    OLLAMA_API_KEY      Required
    OLLAMA_MODEL        Optional (default: kimi-k2.5)
    OLLAMA_TIMEOUT      Optional (default: 30)
"""

import argparse
import json
import os
import ssl
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


@dataclass
class MetaAnalysis:
    """Strukturierte Meta-Analyse"""
    analyzed_at: str
    scorecard_file: str
    strategy_name: str
    analyst_model: str
    
    # Analyse-Ergebnisse
    hypothesis_valid: bool = False
    hypothesis_assessment: str = ""
    data_quality: str = ""
    data_quality_reason: str = ""
    metric_pass: bool = False
    failed_metrics: List[str] = None
    metrics_detail: Dict = None
    walk_forward_pass: bool = False
    wf_degradation_pct: float = 0.0
    wf_robustness_score: float = 0.0
    wf_assessment: str = ""
    vps_fit: bool = False
    vps_notes: Dict = None
    weaknesses: List[str] = None
    hypotheses_next: List[str] = None
    verdict: str = ""
    reason: str = ""
    confidence: float = 0.0
    
    # Raw
    raw_response: str = ""
    execution_time_ms: int = 0
    
    def __post_init__(self):
        if self.failed_metrics is None:
            self.failed_metrics = []
        if self.metrics_detail is None:
            self.metrics_detail = {}
        if self.vps_notes is None:
            self.vps_notes = {}
        if self.weaknesses is None:
            self.weaknesses = []
        if self.hypotheses_next is None:
            self.hypotheses_next = []
    
    def to_dict(self) -> Dict:
        return {
            "analyzed_at": self.analyzed_at,
            "scorecard_file": self.scorecard_file,
            "strategy_name": self.strategy_name,
            "analyst_model": self.analyst_model,
            "analysis": {
                "hypothesis_valid": self.hypothesis_valid,
                "hypothesis_assessment": self.hypothesis_assessment,
                "data_quality": self.data_quality,
                "data_quality_reason": self.data_quality_reason,
                "metric_pass": self.metric_pass,
                "failed_metrics": self.failed_metrics,
                "metrics_detail": self.metrics_detail,
                "walk_forward_pass": self.walk_forward_pass,
                "wf_degradation_pct": self.wf_degradation_pct,
                "wf_robustness_score": self.wf_robustness_score,
                "wf_assessment": self.wf_assessment,
                "vps_fit": self.vps_fit,
                "vps_notes": self.vps_notes,
                "weaknesses": self.weaknesses,
                "hypotheses_next": self.hypotheses_next,
                "verdict": self.verdict,
                "reason": self.reason,
                "confidence": self.confidence
            },
            "execution_time_ms": self.execution_time_ms
        }
    
    def summary(self) -> str:
        """Kompakte Zusammenfassung für CLI"""
        verdict_emoji = {
            "PASS": "✅",
            "FAIL": "❌",
            "TWEAK": "🔧",
            "REJECT": "🚫",
            "INCONCLUSIVE": "❓"
        }.get(self.verdict, "❓")
        
        lines = [
            "",
            "╔" + "═" * 58 + "╗",
            "║" + " KI META-ANALYST REPORT ".center(58) + "║",
            "╠" + "═" * 58 + "╣",
            f"║  Strategie:   {self.strategy_name:<45} ║",
            f"║  Verdict:     {verdict_emoji} {self.verdict:<41} ║",
            f"║  Konfidenz:   {self.confidence*100:.0f}%{''*<43} ║",
            "╠" + "═" * 58 + "╣",
            "║  CHECKS                                    ║",
            f"║    Hypothese:    {'✓' if self.hypothesis_valid else '✗'} Gültig{''*<35} ║",
            f"║    Daten:        {self.data_quality:<10} ({self.data_quality_reason[:20]}...){''*<8} ║",
            f"║    Metriken:     {'✓' if self.metric_pass else '✗'} Pass{''*<37} ║",
            f"║    Walk-Forward: {'✓' if self.walk_forward_pass else '✗'} {f'OOS: {self.wf_degradation_pct:.0f}% Degradation':<33} ║",
            f"║    VPS-Fit:      {'✓' if self.vps_fit else '✗'} Tauglich{''*<33} ║",
            "╠" + "═" * 58 + "╣",
            "║  NÄCHSTE HYPOTHESEN (max 3)              ║",
        ]
        for i, h in enumerate(self.hypotheses_next[:3], 1):
            lines.append(f"║    {i}. {h[:50]:<50} ║")
        lines.extend([
            "╠" + "═" * 58 + "╣",
            "║  BEGRÜNDUNG                              ║",
        ])
        # Wrap reason
        words = self.reason.split()
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 <= 54:
                current_line += (" " if current_line else "") + word
            else:
                lines.append(f"║  {current_line:<54} ║")
                current_line = word
        if current_line:
            lines.append(f"║  {current_line:<54} ║")
        
        lines.extend([
            "╚" + "═" * 58 + "╝",
            ""
        ])
        return "\n".join(lines)


class KimiAnalyst:
    """Ollama Cloud / Kimi 2.5 Meta-Analyst"""
    
    DEFAULT_CONFIG = {
        "api_url": "https://api.ollama.com/v1/chat/completions",
        "model": "kimi-k2.5",
        "timeout": 30,
        "max_tokens": 1000,
        "temperature": 0.2
    }
    
    def __init__(self):
        self.api_key = os.getenv("OLLAMA_API_KEY")
        self.api_url = os.getenv("OLLAMA_API_URL", self.DEFAULT_CONFIG["api_url"])
        self.model = os.getenv("OLLAMA_MODEL", self.DEFAULT_CONFIG["model"])
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", self.DEFAULT_CONFIG["timeout"]))
        self.max_tokens = int(os.getenv("OLLAMA_MAX_TOKENS", self.DEFAULT_CONFIG["max_tokens"]))
    
    def available(self) -> bool:
        """Ist der Analyst konfiguriert?"""
        return self.api_key is not None
    
    def analyze(self, scorecard_path: str) -> MetaAnalysis:
        """Analysiere eine Scorecard mit Kimi."""
        start_time = time.time()
        
        # Lade Scorecard
        with open(scorecard_path, 'r') as f:
            scorecard = json.load(f)
        
        strategy_name = scorecard.get("strategy_name", "unknown")
        
        # Kompaktes Scorecard-JSON für Prompt
        compact_scorecard = self._compact_scorecard(scorecard)
        
        # Baue Prompt
        prompt = self._build_prompt(compact_scorecard)
        
        # Kimi Call
        response = self._call_kimi(prompt)
        
        # Parse Response
        analysis = self._parse_response(
            response, scorecard_path, strategy_name, scorecard,
            int((time.time() - start_time) * 1000)
        )
        
        return analysis
    
    def _compact_scorecard(self, sc: Dict) -> Dict:
        """Reduziere Scorecard auf essentielle Felder"""
        bt = sc.get("backtest_results", {})
        
        return {
            "strategy": sc.get("strategy_name"),
            "hypothesis": sc.get("hypothesis", "")[:150],
            "dataset": sc.get("dataset", {}),
            "results": {
                "net_return": bt.get("net_return"),
                "max_drawdown": bt.get("max_drawdown"),
                "profit_factor": bt.get("profit_factor"),
                "win_rate": bt.get("win_rate"),
                "expectancy": bt.get("expectancy"),
                "trade_count": bt.get("trade_count"),
                "sharpe": bt.get("sharpe_ratio"),
                "stability": bt.get("stability_score")
            },
            "walk_forward": sc.get("walk_forward", {}),
            "resources": sc.get("resource_usage", {}),
            "verdict": sc.get("verdict"),
            "failures": sc.get("failure_reasons", [])
        }
    
    def _build_prompt(self, scorecard: Dict) -> str:
        """Baue den Kimi-Prompt"""
        
        return f"""Du bist der Strategy Lab Analyst. Du analysierst ausschließlich fertige Backtest-Ergebnisse.

## INPUT

**Scorecard:**
```json
{json.dumps(scorecard, indent=2, default=str)}
```

## AUFGABE

Bewerte die Strategie anhand dieser Kriterien:

1. Hypothese-Check: Logisch und testbar?
2. Datenqualität: Trade-Count >30? Zeitraum abgedeckt?
3. Metriken-Check:
   - Profit-Faktor > 1.5?
   - Max-DD < 20%?
   - Win-Rate > 45%?
   - Expectancy > 0?
4. Walk-Forward: OOS stabil? Degradation < 30%?
5. VPS-Fit: execution < 300s, memory < 500MB?
6. Schwachstellen: Wann/wo verliert die Strategie?

## OUTPUT als JSON

```json
{{
  "hypothesis_valid": true,
  "data_quality": "GOOD",
  "data_quality_reason": "45 Trades über 12 Monate",
  "metric_pass": true,
  "failed_metrics": [],
  "metrics_detail": {{
    "profit_factor": {{"value": 1.6, "target": 1.5, "passed": true}},
    "max_drawdown": {{"value": -8.2, "target": -20.0, "passed": true}},
    "win_rate": {{"value": 52.6, "target": 45.0, "passed": true}},
    "expectancy": {{"value": 0.45, "target": 0.0, "passed": true}}
  }},
  "walk_forward_pass": true,
  "wf_degradation_pct": 12.0,
  "wf_assessment": "OOS stabil",
  "vps_fit": true,
  "vps_notes": {{"memory_mb": 128, "execution_s": 4.5}},
  "weaknesses": ["Schwäche in Seitwärtsphasen"],
  "hypotheses_next": ["Volatility-Filter testen", "Exit-Regel verschärfen"],
  "verdict": "PASS",
  "reason": "Solide Performance, robuste Metriken",
  "confidence": 0.85
}}
```

Regeln: Nur Daten verwenden. Keine neuen Backtests. Max 3 Hypothesen. Hart bei Verdicts.
"""
    
    def _call_kimi(self, prompt: str) -> str:
        """HTTP POST an Ollama Cloud"""
        if not self.available():
            return ""
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Du bist ein quantitativer Trading-Analyst. Antworte nur mit validem JSON."},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {
                "temperature": self.DEFAULT_CONFIG["temperature"],
                "num_predict": self.max_tokens
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        try:
            data = json.dumps(payload).encode('utf-8')
            req = Request(self.api_url, data=data, headers=headers, method="POST")
            context = ssl.create_default_context()
            
            with urlopen(req, timeout=self.timeout, context=context) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                return result.get('message', {}).get('content', '')
                
        except HTTPError as e:
            error = e.read().decode('utf-8')[:100]
            return f'{{"error": "HTTP {e.code}: {error}"}}'
        except URLError as e:
            return f'{{"error": "Connection: {str(e)[:100]}"}}'
        except Exception as e:
            return f'{{"error": "{str(e)[:100]}"}}'
    
    def _parse_response(self, response: str, scorecard_path: str,
                       strategy_name: str, scorecard: Dict,
                       execution_time_ms: int) -> MetaAnalysis:
        """Parse Kimi Antwort in MetaAnalysis"""
        from datetime import datetime
        
        parsed = {}
        try:
            # Suche JSON-Block
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
                parsed = json.loads(json_str)
            elif "{" in response:
                json_start = response.find("{")
                json_str = response[json_start:]
                parsed = json.loads(json_str)
            else:
                parsed = json.loads(response)
        except json.JSONDecodeError as e:
            print(f"  ⚠️  JSON Parse Error: {e}")
            parsed = {}
        
        bt = scorecard.get("backtest_results", {})
        wf = scorecard.get("walk_forward", {})
        
        return MetaAnalysis(
            analyzed_at=datetime.now().isoformat(),
            scorecard_file=scorecard_path,
            strategy_name=strategy_name,
            analyst_model=self.model,
            hypothesis_valid=parsed.get("hypothesis_valid", False),
            hypothesis_assessment=parsed.get("hypothesis_assessment", ""),
            data_quality=parsed.get("data_quality", "UNKNOWN"),
            data_quality_reason=parsed.get("data_quality_reason", ""),
            metric_pass=parsed.get("metric_pass", False),
            failed_metrics=parsed.get("failed_metrics", []),
            metrics_detail=parsed.get("metrics_detail", {}),
            walk_forward_pass=parsed.get("walk_forward_pass", False),
            wf_degradation_pct=parsed.get("wf_degradation_pct", 0.0),
            wf_robustness_score=parsed.get("wf_robustness_score", wf.get("robustness_score", 0)),
            wf_assessment=parsed.get("wf_assessment", ""),
            vps_fit=parsed.get("vps_fit", False),
            vps_notes=parsed.get("vps_notes", scorecard.get("resource_usage", {})),
            weaknesses=parsed.get("weaknesses", []),
            hypotheses_next=parsed.get("hypotheses_next", []),
            verdict=parsed.get("verdict", "FAIL"),
            reason=parsed.get("reason", "Parse error"),
            confidence=parsed.get("confidence", 0.0),
            raw_response=response,
            execution_time_ms=execution_time_ms
        )


def fallback_analysis(scorecard_path: str) -> MetaAnalysis:
    """Heuristische Analyse ohne KI"""
    from datetime import datetime
    
    with open(scorecard_path, 'r') as f:
        sc = json.load(f)
    
    bt = sc.get("backtest_results", {})
    
    trade_count = bt.get("trade_count", 0)
    net_return = bt.get("net_return", 0)
    max_dd = bt.get("max_drawdown", 0)
    pf = bt.get("profit_factor", 0)
    wr = bt.get("win_rate", 0)
    exp = bt.get("expectancy", 0)
    
    # Heuristik
    verdict = "TWEAK"
    reason = "Automatische Bewertung (KI nicht verfügbar)"
    metric_pass = False
    
    if trade_count >= 30 and net_return > 5 and max_dd > -20 and pf > 1.3 and wr > 45 and exp > 0:
        verdict = "PASS"
        reason = "Alle Checks bestanden (automatisch)"
        metric_pass = True
    elif trade_count < 10 or net_return < -5:
        verdict = "FAIL"
        reason = "Kritische Metriken nicht erfüllt"
    
    return MetaAnalysis(
        analyzed_at=datetime.now().isoformat(),
        scorecard_file=scorecard_path,
        strategy_name=sc.get("strategy_name", "unknown"),
        analyst_model="heuristic_fallback",
        hypothesis_valid=True,
        hypothesis_assessment="Hypothese nicht bewertet (Fallback)",
        data_quality="GOOD" if trade_count >= 30 else "WARNING",
        data_quality_reason=f"{trade_count} Trades",
        metric_pass=metric_pass,
        failed_metrics=[],
        vps_fit=True,
        verdict=verdict,
        reason=reason,
        confidence=0.5,
        execution_time_ms=100
    )


def main():
    parser = argparse.ArgumentParser(
        description="KI Meta-Analyst für Strategy Scorecards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  %(prog)s --scorecard scorecards/demo_scorecard.json
  %(prog)s --scorecard scorecards/demo_scorecard.json --output my_analysis.json

Environment:
  OLLAMA_API_KEY      Required
  OLLAMA_MODEL        Optional (default: kimi-k2.5)
        """
    )
    
    parser.add_argument('--scorecard', required=True, help='Pfad zur Scorecard JSON')
    parser.add_argument('--output', help='Output Pfad (default: auto)')
    
    args = parser.parse_args()
    
    # Header
    print("\n" + "╔" + "═" * 58 + "╗")
    print("║" + " KI META-ANALYST ".center(58) + "║")
    print("╚" + "═" * 58 + "╝")
    
    if not Path(args.scorecard).exists():
        print(f"\n❌ Fehler: Scorecard nicht gefunden: {args.scorecard}")
        sys.exit(1)
    
    print(f"\n📄 Scorecard: {args.scorecard}")
    
    # Initialisiere Analyst
    analyst = KimiAnalyst()
    
    if not analyst.available():
        print("\n⚠️  OLLAMA_API_KEY nicht gesetzt")
        print("    export OLLAMA_API_KEY='your-key'")
        print("\n    → Nutze Fallback-Heuristik...")
        analysis = fallback_analysis(args.scorecard)
    else:
        print(f"🧠 Model: {analyst.model}")
        print(f"⏱️  Timeout: {analyst.timeout}s")
        print("\n" + "-" * 60)
        print("Analysiere... (max 30 Sekunden)")
        print("-" * 60 + "\n")
        
        analysis = analyst.analyze(args.scorecard)
    
    # Output
    print(analysis.summary())
    
    # Speichern
    if args.output:
        output_path = args.output
    else:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        strategy = analysis.strategy_name.replace(" ", "_").lower()
        scorecard_dir = Path(args.scorecard).parent
        output_path = scorecard_dir / f"meta_analysis_{strategy}_{timestamp}.json"
    
    with open(output_path, 'w') as f:
        json.dump(analysis.to_dict(), f, indent=2)
    
    print(f"✅ Meta-Analyse gespeichert: {output_path}")
    
    # Exit-Code
    sys.exit(0 if analysis.verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
