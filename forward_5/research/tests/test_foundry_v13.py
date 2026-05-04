"""Tests for Foundry V13: Hypothesen-First Strategy Discovery."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "research"))
sys.path.insert(0, str(Path(__file__).parent.parent / "executor"))
sys.path.insert(0, str(Path(__file__).parent))

from run_foundry_v13 import (
    FoundryHypothesis,
    parse_hypothesis,
    expand_to_signal_hypotheses,
    extract_json_array,
    build_prompt,
    ALLOWED_PRIMARY_DRIVERS,
    ALLOWED_SECONDARY_DRIVERS,
)
from sweep_4h_signals import SignalHypothesis


class TestParseHypothesis:
    def test_valid_hypothesis(self):
        raw = {
            "name": "oi_drop_long",
            "intuition": "After large OI drops, forced liquidations clear and price reverts",
            "primary_driver": "oi_pct_change",
            "secondary_driver": "bull200",
            "assets": ["BTC", "ETH"],
            "direction": "long",
            "anti_correlation": "Uses OI dynamics, not funding rate",
        }
        hyp = parse_hypothesis(raw)
        assert hyp is not None
        assert hyp.name == "oi_drop_long"
        assert hyp.primary_driver == "oi_pct_change"
        assert hyp.secondary_driver == "bull200"
        assert hyp.assets == ["BTC", "ETH"]
        assert hyp.direction == "long"

    def test_invalid_primary_driver(self):
        raw = {
            "name": "bad_signal",
            "intuition": "Uses RSI",
            "primary_driver": "rsi",
            "secondary_driver": None,
            "assets": ["BTC"],
            "direction": "long",
            }
        hyp = parse_hypothesis(raw)
        assert hyp is None

    def test_invalid_secondary_driver_ignored(self):
        raw = {
            "name": "test",
            "intuition": "test",
            "primary_driver": "funding_z",
            "secondary_driver": "macd_cross",  # not allowed
            "assets": ["BTC"],
            "direction": "long",
        }
        hyp = parse_hypothesis(raw)
        assert hyp is not None
        assert hyp.secondary_driver is None

    def test_no_assets(self):
        raw = {
            "name": "no_assets",
            "intuition": "test",
            "primary_driver": "funding_z",
            "secondary_driver": None,
            "assets": ["DOGE_COIN"],  # not in allowed list
            "direction": "long",
        }
        hyp = parse_hypothesis(raw)
        assert hyp is None

    def test_defaults_direction(self):
        raw = {
            "name": "test",
            "intuition": "test",
            "primary_driver": "funding_z",
            "secondary_driver": None,
            "assets": ["BTC"],
            "direction": "sideways",  # invalid
        }
        hyp = parse_hypothesis(raw)
        assert hyp is not None
        assert hyp.direction == "long"  # default

    def test_missing_fields(self):
        raw = {}
        hyp = parse_hypothesis(raw)
        assert hyp is None  # no valid primary_driver

    def test_all_primary_drivers_parseable(self):
        for driver in ALLOWED_PRIMARY_DRIVERS:
            raw = {
                "name": f"test_{driver}",
                "intuition": "test",
                "primary_driver": driver,
                "secondary_driver": None,
                "assets": ["BTC"],
                "direction": "long",
            }
            hyp = parse_hypothesis(raw)
            assert hyp is not None, f"Failed for primary_driver={driver}"


class TestExpandToSignalHypotheses:
    def test_funding_z_expansion(self):
        hyp = FoundryHypothesis(
            name="test_funding",
            intuition="test",
            primary_driver="funding_z",
            secondary_driver="bull200",
            assets=["BTC"],
            direction="long",
            timeframe="4h",
            anti_correlation="test",
        )
        signals = expand_to_signal_hypotheses(hyp)
        # 3 z-ranges × 1 bull filter × 2 hold × 2 SL = 12
        assert len(signals) == 12
        # All should be BTC
        assert all(s.asset == "BTC" for s in signals)
        # All should have bull200
        assert all(s.bull_filter == "bull200" for s in signals)

    def test_crosssec_expansion(self):
        hyp = FoundryHypothesis(
            name="test_crosssec",
            intuition="test",
            primary_driver="crosssec_funding_z",
            secondary_driver=None,
            assets=["BTC", "ETH"],
            direction="long",
            timeframe="4h",
            anti_correlation="test",
        )
        signals = expand_to_signal_hypotheses(hyp)
        # 3 z-ranges × 1 bull (none) × 2 hold × 2 SL × 2 assets = 24
        assert len(signals) == 24

    def test_oi_expansion(self):
        hyp = FoundryHypothesis(
            name="test_oi",
            intuition="test",
            primary_driver="oi_pct_change",
            secondary_driver="vol_surge",
            assets=["SOL"],
            direction="long",
            timeframe="4h",
            anti_correlation="test",
        )
        signals = expand_to_signal_hypotheses(hyp)
        # 3 oi ranges × 1 bull (none, vol_surge maps to none) × 2 hold × 2 SL = 12
        assert len(signals) == 12

    def test_multi_asset_expansion(self):
        hyp = FoundryHypothesis(
            name="multi",
            intuition="test",
            primary_driver="funding_z",
            secondary_driver=None,
            assets=["BTC", "ETH", "SOL"],
            direction="long",
            timeframe="4h",
            anti_correlation="test",
        )
        signals = expand_to_signal_hypotheses(hyp)
        # 3 z-ranges × 1 bull (none) × 2 hold × 2 SL × 3 assets = 36
        assert len(signals) == 36

    def test_all_signals_have_valid_asset(self):
        hyp = FoundryHypothesis(
            name="test",
            intuition="test",
            primary_driver="taker_ratio",
            secondary_driver="bull50",
            assets=["BTC", "ETH"],
            direction="long",
            timeframe="4h",
            anti_correlation="test",
        )
        signals = expand_to_signal_hypotheses(hyp)
        for s in signals:
            assert s.asset in ["BTC", "ETH"]
            assert s.hold_hours in [24, 48]
            assert s.sl_pct in [0.0, 5.0]
            assert s.trail_pct == 0.0  # no trailing ever

    def test_short_direction_preserved(self):
        hyp = FoundryHypothesis(
            name="test_short",
            intuition="test",
            primary_driver="funding_z",
            secondary_driver=None,
            assets=["BTC"],
            direction="short",
            timeframe="4h",
            anti_correlation="test",
        )
        signals = expand_to_signal_hypotheses(hyp)
        assert all(s.direction == "short" for s in signals)


class TestExtractJsonArray:
    def test_plain_json(self):
        text = '[{"name": "test"}]'
        result = extract_json_array(text)
        assert len(result) == 1
        assert result[0]["name"] == "test"

    def test_markdown_wrapped(self):
        text = '```json\n[{"name": "test"}]\n```'
        result = extract_json_array(text)
        assert len(result) == 1

    def test_with_surrounding_text(self):
        text = 'Here are the hypotheses:\n[{"name": "a"}, {"name": "b"}]\nThat is all.'
        result = extract_json_array(text)
        assert len(result) == 2

    def test_empty_array(self):
        text = '[]'
        result = extract_json_array(text)
        assert result == []

    def test_invalid_json_returns_empty(self):
        text = 'no json here'
        result = extract_json_array(text)
        assert result == []


class TestBuildPrompt:
    def test_prompt_has_rules_and_features(self):
        prompt = build_prompt([], iteration=1)
        assert "funding_z" in prompt
        assert "DIVERSE" in prompt
        assert "OUTPUT FORMAT" in prompt

    def test_prompt_with_existing_edges(self):
        edges = [{"name": "btc_mild_neg", "primary_driver": "funding_z", "sharpe": 9.05}]
        prompt = build_prompt(edges, iteration=1)
        assert "btc_mild_neg" in prompt

    def test_iteration_2_has_feedback(self):
        prompt = build_prompt([], iteration=2)
        assert "ITERATION 2" in prompt


class TestFoundryHypothesis:
    def test_default_fields(self):
        hyp = FoundryHypothesis(
            name="test", intuition="t", primary_driver="funding_z",
            secondary_driver=None, assets=["BTC"], direction="long",
            timeframe="4h", anti_correlation="t",
        )
        assert hyp.signal_hypotheses == []
        assert hyp.results == []
        assert hyp.best_sharpe == 0.0
        assert hyp.best_result is None
        assert hyp.dsr_pass is False
        assert hyp.cpcv_pass is False
        assert hyp.pbo == 1.0