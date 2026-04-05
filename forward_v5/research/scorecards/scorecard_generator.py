#!/usr/bin/env python3
"""
Scorecard Generator V1
- Erzeugt standardisierte Scorecards
- Harte Bewertungskriterien
- JSON-Export
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any


class ScorecardGenerator:
    """Generator für Strategy Scorecards"""
    
    def __init__(self, output_dir: str = "research/scorecards"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def create(
        self,
        strategy_name: str,
        hypothesis: str,
        dataset: Dict,
        parameters: Dict,
        backtest_results: Dict,
        walk_forward: Dict = None,
        resource_usage: Dict = None,
        failure_reasons: list = None
    ) -> Dict:
        """
        Erstelle Scorecard
        """
        # Bewertung
        verdict = self._determine_verdict(
            backtest_results,
            walk_forward,
            failure_reasons or []
        )
        
        next_actions = self._suggest_next_actions(verdict, backtest_results, walk_forward)
        
        scorecard = {
            "strategy_name": strategy_name,
            "hypothesis": hypothesis,
            "dataset": dataset,
            "parameters": parameters,
            "backtest_results": backtest_results,
            "walk_forward": walk_forward or {},
            "resource_usage": resource_usage or {},
            "failure_reasons": failure_reasons or [],
            "verdict": verdict,
            "next_actions": next_actions,
            "timestamp": datetime.now().isoformat(),
            "scorecard_version": "1.0"
        }
        
        return scorecard
    
    def _determine_verdict(
        self,
        backtest: Dict,
        walk_forward: Dict,
        failures: list
    ) -> str:
        """
        Harte Bewertungslogik
        
        PASS: Robuste Strategie, VPS-tauglich
        FAIL: Klar fehlgeschlagen
        INCONCLUSIVE: Mehr Daten nötig
        REJECT_VPS_UNSAFE: Funktioniert, aber VPS-untauglich
        """
        if failures:
            return "FAIL"
        
        # VPS Safety Check
        resource = backtest.get("resource_usage", {})
        if resource.get("memory_peak_mb", 0) > 1024:  # > 1GB RAM
            return "REJECT_VPS_UNSAFE"
        
        if resource.get("execution_time_ms", 0) > 300000:  # > 5min
            return "REJECT_VPS_UNSAFE"
        
        # Backtest Checks
        if backtest.get("trade_count", 0) < 10:
            return "FAIL"
        
        if backtest.get("max_drawdown", 0) < -50:  # > 50% DD
            return "FAIL"
        
        if backtest.get("net_return", 0) < 0:
            return "FAIL"
        
        # Walk-Forward Check
        if walk_forward and walk_forward.get("n_windows", 0) > 0:
            if not walk_forward.get("passed", False):
                return "INCONCLUSIVE"
            
            if walk_forward.get("robustness_score", 0) < 60:
                return "INCONCLUSIVE"
        
        return "PASS"
    
    def _suggest_next_actions(
        self,
        verdict: str,
        backtest: Dict,
        walk_forward: Dict
    ) -> list:
        """Empfohlene nächste Schritte basierend auf Verdict"""
        
        if verdict == "PASS":
            return [
                "Integrate into forward_v5 system",
                "Paper trade validation",
                "Prepare live-ready config"
            ]
        
        if verdict == "FAIL":
            reasons = []
            if backtest.get("trade_count", 0) < 10:
                reasons.append("Increase trade frequency")
            if backtest.get("net_return", 0) < 0:
                reasons.append("Refine entry/exit logic")
            if backtest.get("max_drawdown", 0) < -50:
                reasons.append("Add risk controls")
            return reasons or ["Revisit hypothesis", "Test on different timeframe"]
        
        if verdict == "INCONCLUSIVE":
            return [
                "Extend test period",
                "Run additional walk-forward windows",
                "Test on different market conditions"
            ]
        
        if verdict == "REJECT_VPS_UNSAFE":
            return [
                "Optimize for lower memory usage",
                "Reduce parameter grid size",
                "Consider: Is this strategy viable for this infrastructure?"
            ]
        
        return []
    
    def save(self, scorecard: Dict, filename: str = None) -> str:
        """Speichere Scorecard als JSON"""
        
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            strategy = scorecard["strategy_name"].replace(" ", "_").lower()
            filename = f"scorecard_{strategy}_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(scorecard, f, indent=2)
        
        print(f"✓ Scorecard saved: {filepath}")
        return str(filepath)
    
    def load(self, filename: str) -> Dict:
        """Lade Scorecard"""
        filepath = self.output_dir / filename
        
        with open(filepath, 'r') as f:
            return json.load(f)
    
    def summary(self, scorecard: Dict) -> str:
        """Kurze Zusammenfassung für CLI"""
        return f"""
╔══════════════════════════════════════════════════════════╗
║  SCORECARD: {scorecard['strategy_name'][:40]:<40} ║
╠══════════════════════════════════════════════════════════╣
║  Verdict: {scorecard['verdict']:<45} ║
║  Return: {scorecard['backtest_results'].get('net_return', 0):>8.2f}%{'':<37} ║
║  Drawdown: {scorecard['backtest_results'].get('max_drawdown', 0):>8.2f}%{'':<35} ║
║  Trades: {scorecard['backtest_results'].get('trade_count', 0):>8}{'':<40} ║
║  W-F Robustness: {scorecard.get('walk_forward', {}).get('robustness_score', 'N/A'):>8}{'':<33} ║
╚══════════════════════════════════════════════════════════╝
        """.strip()


if __name__ == "__main__":
    gen = ScorecardGenerator()
    print("Scorecard Generator V1")
    print(f"Output: {gen.output_dir}")
