#!/usr/bin/env python3
"""
KI Meta-Analyst — Ollama Cloud / Kimi 2.5

Analysiert Scorecards und liefert:
- Hypothesen-Bewertung
- Schwachstellen-Clustering  
- Konkrete Verbesserungsvorschläge
- Nächste Experimente

VPS-First:
- Nur HTTP stdlib (kein ollama-python package)
- Kurze Timeouts (30s)
- Kompakte Prompts (Token-sparend)
- Keine Massen-Analysen
"""

import json
import os
import ssl
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


@dataclass
class AnalystConfig:
    """Konfiguration für Ollama Cloud"""
    api_url: str = "https://api.ollama.com/v1/chat/completions"
    model: str = "kimi-k2.5"  # Ollama Cloud Modell
    api_key: Optional[str] = None
    timeout: int = 30  # Sekunden
    max_tokens: int = 800  # Kompakte Antworten
    temperature: float = 0.3  # Faktisch, nicht kreativ
    
    @classmethod
    def from_env(cls) -> 'AnalystConfig':
        """Lade aus Umgebungsvariablen"""
        return cls(
            api_url=os.getenv('OLLAMA_API_URL', cls.api_url),
            model=os.getenv('OLLAMA_MODEL', cls.model),
            api_key=os.getenv('OLLAMA_API_KEY'),
            timeout=int(os.getenv('OLLAMA_TIMEOUT', '30')),
            max_tokens=int(os.getenv('OLLAMA_MAX_TOKENS', '800'))
        )
    
    def validate(self) -> bool:
        """Prüfe ob API Key vorhanden"""
        return self.api_key is not None


class KIAnalyst:
    """
    Meta-Analyst für Strategy Scorecards
    
    Usage:
        analyst = KIAnalyst()
        if analyst.available():
            report = analyst.analyze_scorecard(scorecard)
            print(report.summary())
    """
    
    def __init__(self, config: Optional[AnalystConfig] = None):
        self.config = config or AnalystConfig.from_env()
        self._available = self.config.validate()
    
    def available(self) -> bool:
        """Ist der Analyst nutzbar?"""
        return self._available
    
    def _call_api(self, messages: List[Dict]) -> Optional[str]:
        """
        HTTP POST an Ollama Cloud
        Nutzt nur Standard-Library (kein requests/httpx)
        """
        if not self.available():
            return None
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}"
        }
        
        try:
            data = json.dumps(payload).encode('utf-8')
            req = Request(
                self.config.api_url,
                data=data,
                headers=headers,
                method="POST"
            )
            
            # Timeout und SSL
            context = ssl.create_default_context()
            
            with urlopen(req, timeout=self.config.timeout, context=context) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                return result.get('message', {}).get('content', '').strip()
                
        except HTTPError as e:
            error_body = e.read().decode('utf-8')
            return f"[API Error {e.code}: {error_body[:100]}]"
            
        except URLError as e:
            return f"[Connection Error: {str(e)[:100]}]"
            
        except Exception as e:
            return f"[Error: {str(e)[:100]}]"
    
    def analyze_scorecard(self, scorecard: Dict) -> 'AnalystReport':
        """
        Analysiere eine Scorecard
        
        Liefert:
        - Hypothesen-Stärke
        - Datenqualität
        - Risiko-Cluster
        - Verbesserungsvorschläge (max 3)
        """
        
        # Kompakte Scorecard-Serialisierung
        compact = self._compact_scorecard(scorecard)
        
        # Prompt 1: Hypothesen-Analyse
        hypothesis_prompt = self._build_hypothesis_prompt(compact)
        hypothesis_analysis = self._call_api([
            {"role": "system", "content": "You are a quantitative trading analyst. Be factual, concise, data-driven."},
            {"role": "user", "content": hypothesis_prompt}
        ]) or "[Analysis unavailable - check OLLAMA_API_KEY]"
        
        # Prompt 2: Verbesserungsvorschläge
        improvement_prompt = self._build_improvement_prompt(compact)
        improvements = self._call_api([
            {"role": "system", "content": "You are a strategy optimization expert. Focus on actionable changes."},
            {"role": "user", "content": improvement_prompt}
        ]) or "[Suggestions unavailable]"
        
        return AnalystReport(
            strategy=scorecard.get('strategy_name', 'unknown'),
            verdict=scorecard.get('verdict', 'UNKNOWN'),
            hypothesis_analysis=hypothesis_analysis,
            improvements=improvements,
            next_experiments=self._extract_next_experiments(improvements)
        )
    
    def _compact_scorecard(self, sc: Dict) -> str:
        """Extrahiere nur relevante Daten für den Prompt"""
        bt = sc.get('backtest_results', {})
        wf = sc.get('walk_forward', {})
        
        lines = [
            f"Strategy: {sc.get('strategy_name', 'N/A')}",
            f"Hypothesis: {sc.get('hypothesis', 'N/A')[:100]}...",
            f"Dataset: {sc.get('dataset', {}).get('symbol', 'N/A')}",
            f"Timeframe: {sc.get('dataset', {}).get('timeframe', 'N/A')}",
            f"",
            f"Results:",
            f"- Net Return: {bt.get('net_return', 0):.2f}%",
            f"- Max Drawdown: {bt.get('max_drawdown', 0):.2f}%",
            f"- Profit Factor: {bt.get('profit_factor', 0):.2f}",
            f"- Win Rate: {bt.get('win_rate', 0):.1f}%",
            f"- Trade Count: {bt.get('trade_count', 0)}",
            f"- Expectancy: {bt.get('expectancy', 0):.3f}",
            f"",
            f"Walk-Forward:",
            f"- Robustness: {wf.get('robustness_score', 'N/A')}",
            f"- Passed: {wf.get('passed', False)}",
            f"",
            f"Resource:",
            f"- Memory: {sc.get('resource_usage', {}).get('memory_peak_mb', 'N/A')} MB",
            f"- Time: {sc.get('resource_usage', {}).get('execution_time_ms', 'N/A')} ms",
            f"",
            f"Failures: {sc.get('failure_reasons', [])}",
            f"Verdict: {sc.get('verdict', 'N/A')}"
        ]
        
        return "\n".join(lines)
    
    def _build_hypothesis_prompt(self, compact: str) -> str:
        """Prompt für Hypothesen-Analyse"""
        return f"""Analyze this trading strategy scorecard:

{compact}

Evaluate:
1. Is the hypothesis testable and logical? (1-2 sentences)
2. Is the sample size adequate (>30 trades)? Yes/No
3. Is the result believable or overfit? (data-driven assessment)
4. What is the weakest assumption in this strategy?

Be concise. Max 200 words."""
    
    def _build_improvement_prompt(self, compact: str) -> str:
        """Prompt für Verbesserungen"""
        return f"""Based on this scorecard:

{compact}

Suggest EXACTLY 3 concrete improvements:

1. [Parameter/Logic change] → Expected impact
2. [Risk management change] → Expected impact  
3. [Data/Timeframe change] → Expected impact

Format as actionable bullet points. No fluff."""
    
    def _extract_next_experiments(self, improvements_text: str) -> List[str]:
        """Extrahiere nächste Experimente aus Verbesserungen"""
        # Einfache Extraktion – in Praxis könnte KI strukturiertes JSON liefern
        lines = [l.strip() for l in improvements_text.split('\n') if l.strip() and l[0].isdigit()]
        return lines[:3]


@dataclass
class AnalystReport:
    """Ergebnis einer KI-Analyse"""
    strategy: str
    verdict: str
    hypothesis_analysis: str
    improvements: str
    next_experiments: List[str]
    
    def summary(self) -> str:
        """Kompakte Zusammenfassung für CLI"""
        return f"""
╔══════════════════════════════════════════════════════════╗
║  KI ANALYST REPORT: {self.strategy[:35]:<35} ║
╠══════════════════════════════════════════════════════════╣
║  Verdict: {self.verdict:<45} ║
╠══════════════════════════════════════════════════════════╣
HYPOTHESIS ANALYSIS:
{self._truncate(self.hypothesis_analysis, 250)}

IMPROVEMENTS:
{self._truncate(self.improvements, 300)}

NEXT EXPERIMENTS:
{chr(10).join(f"  {i+1}. {e[:60]}" for i, e in enumerate(self.next_experiments))}
╚══════════════════════════════════════════════════════════╝"""
    
    def save(self, filepath: str):
        """Speichere als JSON"""
        with open(filepath, 'w') as f:
            json.dump({
                'strategy': self.strategy,
                'verdict': self.verdict,
                'hypothesis_analysis': self.hypothesis_analysis,
                'improvements': self.improvements,
                'next_experiments': self.next_experiments
            }, f, indent=2)
    
    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."


def check_analyst_availability() -> bool:
    """Schneller Check ob Analyst konfiguriert ist"""
    return bool(os.getenv('OLLAMA_API_KEY'))


if __name__ == "__main__":
    print("KI Meta-Analyst V1")
    print(f"Status: {'✓ Available' if check_analyst_availability() else '✗ Not configured'}")
    print(f"")
    print("Usage:")
    print("  export OLLAMA_API_KEY='your-key'")
    print("  python analyst.py  # Run standalone check")
