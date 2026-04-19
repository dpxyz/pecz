"""
Gate Evaluator v0.1 – 5 harte Gates, keine KI

Liest Backtest-Results + Spec, prüft binär: PASS oder FAIL.
Keine Meinungen. Keine KI. Nur Mathematik.

G1: Profitability  (Return, PF, Expectancy, Trade Count)
G2: Risk           (Drawdown, Return/DD Ratio, Consecutive Losses)
G3: Robustness     (Walk-Forward, Degradation, Sharpe)
G4: Resources      (Memory, Execution Time, CPU)
G5: Guardrails     (Param Combinations, Assets, Lookback)
"""

import json
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GateResult:
    gate_name: str
    passed: bool
    checks: list[dict] = field(default_factory=list)  # {name, value, threshold, passed}
    
    def add_check(self, name: str, value: float, threshold: float, operator: str = ">="):
        if operator == ">=":
            passed = value >= threshold
        elif operator == "<=":
            passed = value <= threshold
        elif operator == ">":
            passed = value > threshold
        elif operator == "<":
            passed = value < threshold
        else:
            raise ValueError(f"Unknown operator: {operator}")
        
        self.checks.append({
            "name": name,
            "value": round(value, 6),
            "threshold": round(threshold, 6),
            "operator": operator,
            "passed": passed
        })
        if not passed:
            self.passed = False


def evaluate_g1_profitability(results: dict, spec: dict) -> GateResult:
    """G1: Profitability Gate"""
    gate = GateResult("G1_profitability", True)
    sp = spec.get("profitability", {})
    bt = results.get("backtest_results", {})
    
    gate.add_check("net_return_pct", bt.get("net_return", 0) * 100, sp.get("min_return_pct", 5.0), ">=")
    gate.add_check("profit_factor", bt.get("profit_factor", 0), sp.get("min_profit_factor", 1.5), ">=")
    gate.add_check("expectancy", bt.get("expectancy", 0), sp.get("min_expectancy", 0.01), ">")
    gate.add_check("trade_count", bt.get("trade_count", 0), sp.get("min_trades", 50), ">=")
    
    return gate


def evaluate_g2_risk(results: dict, spec: dict) -> GateResult:
    """G2: Risk Gate"""
    gate = GateResult("G2_risk", True)
    sp = spec.get("risk", {})
    bt = results.get("backtest_results", {})
    
    net_return = bt.get("net_return", 0) * 100
    max_dd = bt.get("max_drawdown", 0)
    
    gate.add_check("max_drawdown_pct", max_dd, sp.get("max_drawdown_pct", 15.0), "<=")
    
    # Return/DD Ratio
    return_dd_ratio = net_return / max_dd if max_dd > 0 else 0
    gate.add_check("return_dd_ratio", return_dd_ratio, sp.get("min_return_dd_ratio", 0.33), ">=")
    
    gate.add_check("max_consecutive_losses", 
                   bt.get("max_consecutive_losses", 99), 
                   sp.get("max_consecutive_losses", 8), "<=")
    
    return gate


def evaluate_g3_robustness(results: dict, spec: dict) -> GateResult:
    """G3: Robustness Gate"""
    gate = GateResult("G3_robustness", True)
    sp = spec.get("robustness", {})
    wf = results.get("walk_forward", {})
    
    gate.add_check("wf_windows_profitable", 
                   wf.get("windows_profitable", 0), 
                   sp.get("wf_windows_profitable", 2), ">=")
    gate.add_check("wf_degradation_pct", 
                   wf.get("degradation_pct", 100), 
                   sp.get("wf_max_degradation_pct", 40), "<=")
    gate.add_check("sharpe_ratio", 
                   results.get("backtest_results", {}).get("sharpe_ratio", 0), 
                   sp.get("min_sharpe_ratio", 0.5), ">=")
    
    return gate


def evaluate_g4_resources(results: dict, spec: dict) -> GateResult:
    """G4: Resource Gate"""
    gate = GateResult("G4_resources", True)
    sp = spec.get("resources", {})
    res = results.get("backtest_results", {}).get("resource_usage", {})
    
    gate.add_check("memory_peak_mb", 
                   res.get("memory_peak_mb", 999), 
                   sp.get("max_memory_mb", 256), "<=")
    gate.add_check("execution_time_s", 
                   res.get("execution_time_ms", 99999) / 1000, 
                   sp.get("max_execution_s", 30), "<=")
    gate.add_check("cpu_avg_pct", 
                   res.get("cpu_avg_pct", 99), 
                   sp.get("max_cpu_pct", 50), "<=")
    
    return gate


def evaluate_g5_guardrails(candidate: dict, spec: dict) -> GateResult:
    """G5: Guardrail Gate (from candidate, not backtest)"""
    gate = GateResult("G5_guardrails", True)
    sp = spec.get("guardrails", {})
    strategy = candidate.get("strategy", {})
    
    # Count parameter combinations
    indicators = strategy.get("indicators", [])
    total_combos = 1
    for ind in indicators:
        params = ind.get("params", {})
        total_combos *= len(params) if len(params) > 0 else 1
    total_combos = max(total_combos, len(indicators))
    
    gate.add_check("param_combinations", 
                   float(total_combos), 
                   float(sp.get("max_param_combinations", 50)), "<=")
    gate.add_check("asset_count", 
                   float(len(strategy.get("assets", []))), 
                   float(sp.get("max_assets", 3)), "<=")
    
    # Check lookback (max period across indicators)
    max_lookback = max(
        (ind.get("params", {}).get("period", 0) for ind in indicators), 
        default=0
    )
    gate.add_check("max_lookback_bars", 
                   float(max_lookback), 
                   float(sp.get("max_lookback_bars", 500)), "<=")
    
    return gate


def evaluate_all(results: dict, candidate: dict, spec: dict) -> dict:
    """Run all 5 gates. Returns full evaluation."""
    gates = [
        evaluate_g1_profitability(results, spec),
        evaluate_g2_risk(results, spec),
        evaluate_g3_robustness(results, spec),
        evaluate_g4_resources(results, spec),
        evaluate_g5_guardrails(candidate, spec),
    ]
    
    all_passed = all(g.passed for g in gates)
    failed_gates = [g.gate_name for g in gates if not g.passed]
    passed_gates = [g.gate_name for g in gates if g.passed]
    
    # Build improvement hints from failed checks
    hints = []
    for g in gates:
        for c in g.checks:
            if not c["passed"]:
                hints.append(f"{g.gate_name}.{c['name']}: {c['value']} {c['operator']} {c['threshold']} → FAIL")
    
    return {
        "verdict": "PASS" if all_passed else "FAIL",
        "all_gates_passed": all_passed,
        "passed_gates": passed_gates,
        "failed_gates": failed_gates,
        "gates": {
            g.gate_name: {
                "passed": g.passed,
                "checks": g.checks
            } for g in gates
        },
        "improvement_hints": hints
    }


if __name__ == "__main__":
    # Load spec
    spec_path = Path(__file__).parent / "spec.yaml"
    with open(spec_path) as f:
        spec = yaml.safe_load(f)
    
    # Example: Test with existing scorecard data
    example_results = {
        "backtest_results": {
            "net_return": 0.0085,
            "max_drawdown": 30.45,
            "profit_factor": 1.007,
            "win_rate": 58.89,
            "expectancy": 0.009,
            "trade_count": 90,
            "sharpe_ratio": 0.12,
            "max_consecutive_losses": 7,
            "resource_usage": {
                "execution_time_ms": 1930,
                "memory_peak_mb": 128.0,
                "cpu_avg_pct": 12
            }
        },
        "walk_forward": {
            "windows_profitable": 3,
            "degradation_pct": 25
        }
    }
    
    example_candidate = {
        "strategy": {
            "name": "mean_reversion_panic",
            "assets": ["BTCUSDT"],
            "indicators": [
                {"name": "SMA", "params": {"period": 60}},
                {"name": "ZSCORE", "params": {"period": 50}}
            ]
        }
    }
    
    result = evaluate_all(example_results, example_candidate, spec)
    print(json.dumps(result, indent=2))
    print(f"\nVerdict: {result['verdict']}")
    if result['failed_gates']:
        print(f"Failed: {result['failed_gates']}")
        print("Hints:")
        for h in result['improvement_hints']:
            print(f"  {h}")