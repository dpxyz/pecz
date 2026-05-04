"""Tests for Edge Registry"""

import pytest
import json
import tempfile
from pathlib import Path
from edge_registry import EdgeRegistry, EdgeRecord, PORTFOLIO_RHO_THRESHOLD


@pytest.fixture
def tmp_registry(tmp_path):
    """Create a temporary registry for testing."""
    return EdgeRegistry(path=tmp_path / "test_registry.json")


class TestEdgeRegistry:
    def test_empty_registry(self, tmp_registry):
        assert len(tmp_registry.edges) == 0
    
    def test_register_edge(self, tmp_registry):
        edge = EdgeRecord(
            edge_id="test_edge_1",
            name="Test Edge",
            primary_driver="funding_rate",
            secondary_driver="ema200",
            assets=["BTC", "ETH"],
            timeframe="4h",
            entry_logic="funding z > 0.5",
            exit_logic="24h time exit",
            parameters={"z_threshold": 0.5},
        )
        tmp_registry.register(edge)
        assert "test_edge_1" in tmp_registry.edges
        assert tmp_registry.edges["test_edge_1"].status == "candidate"
    
    def test_register_duplicate_updates(self, tmp_registry):
        edge = EdgeRecord(
            edge_id="test_edge_1", name="V1",
            primary_driver="funding", secondary_driver="none",
            assets=["BTC"], timeframe="4h",
            entry_logic="test", exit_logic="test", parameters={},
        )
        tmp_registry.register(edge)
        edge_v2 = EdgeRecord(
            edge_id="test_edge_1", name="V2",
            primary_driver="funding", secondary_driver="ema",
            assets=["BTC", "ETH"], timeframe="4h",
            entry_logic="test2", exit_logic="test2", parameters={},
        )
        tmp_registry.register(edge_v2)
        assert tmp_registry.edges["test_edge_1"].name == "V2"
    
    def test_promote_edge(self, tmp_registry):
        edge = EdgeRecord(
            edge_id="test_edge_1", name="Test",
            primary_driver="funding", secondary_driver="none",
            assets=["BTC"], timeframe="4h",
            entry_logic="test", exit_logic="test", parameters={},
        )
        tmp_registry.register(edge)
        
        assert tmp_registry.promote("test_edge_1", "validated") is True
        assert tmp_registry.edges["test_edge_1"].status == "validated"
        assert tmp_registry.edges["test_edge_1"].validated_at != ""
    
    def test_invalid_status(self, tmp_registry):
        result = tmp_registry.promote("nonexistent", "invalid_status")
        assert result is False
    
    def test_get_production_edges(self, tmp_registry):
        for i, status in enumerate(["candidate", "production", "deprecated"]):
            edge = EdgeRecord(
                edge_id=f"edge_{i}", name=f"Edge {i}",
                primary_driver="test", secondary_driver="test",
                assets=["BTC"], timeframe="4h",
                entry_logic="test", exit_logic="test", parameters={},
                status=status,
            )
            tmp_registry.register(edge)
        
        prod = tmp_registry.get_production_edges()
        assert len(prod) == 1
        assert prod[0].edge_id == "edge_1"
    
    def test_seed_known_edges(self, tmp_registry):
        tmp_registry.seed_known_edges()
        edges = tmp_registry.get_all_edges()
        assert len(edges) >= 2
        # SOL champion should be in production
        prod = tmp_registry.get_production_edges()
        assert any(e.edge_id == "SOL_mild_neg_funding" for e in prod)
    
    def test_persistence(self, tmp_path):
        """Registry saves and loads correctly."""
        path = tmp_path / "persist_test.json"
        reg1 = EdgeRegistry(path=path)
        edge = EdgeRecord(
            edge_id="persist_test", name="Persist",
            primary_driver="funding", secondary_driver="none",
            assets=["BTC"], timeframe="4h",
            entry_logic="test", exit_logic="test", parameters={},
        )
        reg1.register(edge)
        
        # Load fresh instance
        reg2 = EdgeRegistry(path=path)
        assert "persist_test" in reg2.edges
        assert reg2.edges["persist_test"].name == "Persist"
    
    def test_portfolio_rho_threshold(self):
        assert PORTFOLIO_RHO_THRESHOLD == 0.4


class TestEdgeRecord:
    def test_default_values(self):
        edge = EdgeRecord(
            edge_id="test", name="Test",
            primary_driver="funding", secondary_driver="none",
            assets=["BTC"], timeframe="4h",
            entry_logic="test", exit_logic="test", parameters={},
        )
        assert edge.status == "candidate"
        assert edge.is_annualized_sharpe == 0.0
        assert edge.dsr == 0.0
        assert edge.correlation_vector == {}
    
    def test_serialization(self):
        edge = EdgeRecord(
            edge_id="test", name="Test",
            primary_driver="funding", secondary_driver="none",
            assets=["BTC", "ETH"], timeframe="4h",
            entry_logic="test", exit_logic="test", parameters={"z": 0.5},
        )
        from dataclasses import asdict
        d = asdict(edge)
        assert d["edge_id"] == "test"
        assert d["assets"] == ["BTC", "ETH"]
        # Should be JSON serializable
        json.dumps(d)