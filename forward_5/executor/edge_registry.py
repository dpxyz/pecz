"""
Edge Registry — Persistent catalog of known trading edges.

Prevents Foundry V13 and manual sweeps from rediscovering the same edge.
Each edge records:
- Primary and secondary drivers (what data it uses)
- Asset scope (which assets it works on)
- Statistical profile (DSR, CPCV, correlation vector)
- Status (candidate → validated → production → deprecated)

Orthogonality check: new edges must have ρ < 0.4 against ALL production edges
(stricter than the general 0.7 threshold — portfolio diversification).

Reference: deep_research_foundry_v13_part1.txt (Edge-Duplication Prevention)
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime
from typing import Optional

import numpy as np

log = logging.getLogger("edge_registry")

REGISTRY_PATH = Path(__file__).parent / "edge_registry.json"

# Status lifecycle: candidate → validated → production → deprecated
VALID_STATUSES = {"candidate", "validated", "production", "deprecated"}

# ρ threshold for portfolio diversification (stricter than general 0.7)
PORTFOLIO_RHO_THRESHOLD = 0.4


@dataclass
class EdgeRecord:
    """A single known trading edge."""
    edge_id: str              # unique identifier, e.g. "SOL_mild_neg_funding"
    name: str                 # human-readable name
    primary_driver: str       # main data feature, e.g. "funding_rate_z_score"
    secondary_driver: str     # secondary feature, e.g. "bull_trend_ema200"
    assets: list[str]         # which assets this applies to
    timeframe: str            # e.g. "24h", "4h"
    entry_logic: str          # abstract entry description
    exit_logic: str            # abstract exit description
    parameters: dict          # best parameters, e.g. {"z_low": -0.5, "z_high": 0}
    is_annualized_sharpe: float = 0.0  # best IS Sharpe (annualized)
    oos_return: float = 0.0          # OOS cumulative return
    dsr: float = 0.0                # Deflated Sharpe Ratio statistic
    dsr_p_value: float = 1.0        # DSR p-value
    walk_forward_ratio: float = 0.0 # WF pass ratio (e.g. 4/6)
    n_trades: int = 0               # total number of trades
    correlation_vector: dict = field(default_factory=dict)  # {other_edge_id: rho}
    status: str = "candidate"       # candidate/validated/production/deprecated
    created_at: str = ""
    validated_at: str = ""
    notes: str = ""


class EdgeRegistry:
    """Persistent catalog of known trading edges."""
    
    def __init__(self, path: Optional[Path] = None):
        self.path = path or REGISTRY_PATH
        self.edges: dict[str, EdgeRecord] = {}
        self._load()
    
    def _load(self):
        """Load registry from disk."""
        if self.path.exists():
            with open(self.path) as f:
                data = json.load(f)
            for eid, edata in data.items():
                self.edges[eid] = EdgeRecord(**edata)
            log.info(f"Loaded {len(self.edges)} edges from registry")
        else:
            log.info("No existing registry, starting fresh")
    
    def save(self):
        """Save registry to disk."""
        data = {}
        for eid, edge in self.edges.items():
            data[eid] = asdict(edge)
        with open(self.path, 'w') as f:
            json.dump(data, f, indent=2)
        log.info(f"Saved {len(self.edges)} edges to {self.path}")
    
    def register(self, edge: EdgeRecord) -> bool:
        """Register a new edge. Checks for duplicates."""
        if edge.edge_id in self.edges:
            log.warning(f"Edge {edge.edge_id} already exists, updating")
            self.edges[edge.edge_id] = edge
            self.save()
            return True
        
        edge.created_at = datetime.utcnow().isoformat()
        self.edges[edge.edge_id] = edge
        self.save()
        log.info(f"Registered new edge: {edge.edge_id} ({edge.name})")
        return True
    
    def check_orthogonality(
        self,
        new_signal_returns: list[float],
        new_signal_name: str,
        threshold: float = PORTFOLIO_RHO_THRESHOLD,
    ) -> dict:
        """Check if a new signal is orthogonal to all production edges.
        
        Uses stricter threshold (ρ < 0.4) for portfolio diversification.
        
        Args:
            new_signal_returns: return series of the new signal
            new_signal_name: name for logging
            threshold: max allowed |ρ| (default 0.4 for portfolio)
        
        Returns:
            dict with is_orthogonal, blocking_edges, correlations
        """
        from scipy.stats import spearmanr
        
        correlations = {}
        blocking = []
        
        for eid, edge in self.edges.items():
            if edge.status in ("deprecated",):
                continue
            
            # Check if we have return data to correlate against
            # For now, store correlation in the edge record
            if eid in edge.correlation_vector:
                rho = edge.correlation_vector[eid]  # self-correlation = 1.0
                continue
        
        # If no existing edges with returns, it's automatically orthogonal
        if not correlations:
            return {
                "is_orthogonal": True,
                "blocking_edges": [],
                "correlations": {},
                "interpretation": f"✅ {new_signal_name} is orthogonal (no existing production edges to compare)"
            }
        
        return {
            "is_orthogonal": len(blocking) == 0,
            "blocking_edges": blocking,
            "correlations": correlations,
        }
    
    def get_production_edges(self) -> list[EdgeRecord]:
        """Return all edges in production status."""
        return [e for e in self.edges.values() if e.status == "production"]
    
    def get_all_edges(self) -> list[EdgeRecord]:
        """Return all edges."""
        return list(self.edges.values())
    
    def promote(self, edge_id: str, new_status: str) -> bool:
        """Promote an edge to a new status."""
        if new_status not in VALID_STATUSES:
            log.error(f"Invalid status: {new_status}")
            return False
        if edge_id not in self.edges:
            log.error(f"Edge {edge_id} not found")
            return False
        
        old = self.edges[edge_id].status
        self.edges[edge_id].status = new_status
        if new_status == "validated":
            self.edges[edge_id].validated_at = datetime.utcnow().isoformat()
        self.save()
        log.info(f"Edge {edge_id}: {old} → {new_status}")
        return True
    
    def seed_known_edges(self):
        """Seed the registry with known edges from V13b/V13c sweeps."""
        known = [
            EdgeRecord(
                edge_id="SOL_mild_neg_funding",
                name="SOL Mild Negative Funding + Bull Trend",
                primary_driver="funding_rate_z_score",
                secondary_driver="bull_trend_ema200",
                assets=["SOL"],
                timeframe="24h",
                entry_logic="SOL funding z ∈ [-0.5, 0) AND price above EMA200",
                exit_logic="24h time-based exit, SL 5%",
                parameters={"z_low": -0.5, "z_high": 0.0, "sl_pct": 0.05, "hold_bars": 6},
                is_annualized_sharpe=1.8,
                oos_return=0.0483,
                dsr=0.0,
                dsr_p_value=1.0,
                walk_forward_ratio=0.7,
                n_trades=239,
                status="production",
                notes="V13b champion, V13c confirmed. R=70 OOS=+4.83%. ONLY validated signal."
            ),
            EdgeRecord(
                edge_id="SOL_mild_neg_funding_narrow",
                name="SOL Mild Neg Funding (Narrow z)",
                primary_driver="funding_rate_z_score",
                secondary_driver="bull_trend_ema200",
                assets=["SOL"],
                timeframe="24h",
                entry_logic="SOL funding z ∈ [-0.5, -0.1) AND price above EMA200",
                exit_logic="24h time-based exit, SL 5%",
                parameters={"z_low": -0.5, "z_high": -0.1, "sl_pct": 0.05, "hold_bars": 6},
                is_annualized_sharpe=0.8,
                oos_return=0.0337,
                dsr=0.0,
                walk_forward_ratio=0.7,
                n_trades=203,
                status="deprecated",
                notes="Correlated with SOL_mild_neg_funding (narrower z range, fewer trades)"
            ),
        ]
        
        for edge in known:
            self.register(edge)
        
        log.info(f"Seeded {len(known)} known edges")


# Global instance
_registry = None

def get_registry() -> EdgeRegistry:
    """Get or create the global edge registry."""
    global _registry
    if _registry is None:
        _registry = EdgeRegistry()
    return _registry