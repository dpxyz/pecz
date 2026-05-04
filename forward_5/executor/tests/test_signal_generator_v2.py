"""
Tests for V2 Engine — SignalGenerator + DataFeed + Paper Engine
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from signal_generator_v2 import SignalGeneratorV2, SignalType, Signal


# ── SignalGeneratorV2 Tests ──

class TestSignalGeneratorV2:
    """Test funding-first signal logic."""

    def setup_method(self):
        self.gen = SignalGeneratorV2()
        # Create minimal candle data (210 candles needed for EMA200)
        self.candles = []
        base_price = 25.0
        for i in range(250):
            self.candles.append({
                "timestamp": 1700000000000 + i * 3600000,
                "open": base_price + i * 0.01,
                "high": base_price + i * 0.01 + 0.5,
                "low": base_price + i * 0.01 - 0.5,
                "close": base_price + i * 0.01,
                "volume": 1000,
                "symbol": "AVAXUSDT",
            })

    def test_avax_archived(self):
        """AVAX: Archived — bear-only, failed WF Gate."""
        for c in self.candles:
            c["symbol"] = "AVAXUSDT"
        sig = self.gen.evaluate(self.candles, funding_z=-1.5, bull200=True)
        assert sig.type == SignalType.SIGNAL_FLAT
        assert "no V2 signal" in sig.reason

    def test_btc_bear_fgi_none_allows_signal(self):
        """Bug 4 regression: FGI=None should NOT block BTC bear signals.
        
        If FGI API fails, FGI=None. The original code blocked all BTC bear
        signals when FGI was None because `fgi is not None and fgi < 40`
        evaluated to False, falling into the else branch (no signal).
        
        Fix: FGI=None should be treated as 'unknown, allow signal' (conservative
        assumption that fear may be present).
        """
        for c in self.candles:
            c["symbol"] = "BTCUSDT"

        # Bear + z<-1 + FGI=None → should allow signal (not block it)
        sig = self.gen.evaluate(self.candles, funding_z=-1.5, bull200=False, fgi=None)
        assert sig.type == SignalType.SIGNAL_LONG, (
            f"FGI=None should not block BTC bear signal. Got: {sig.reason}"
        )
        assert "FGI=None" in sig.reason or "bear" in sig.reason.lower()

    def test_btc_bear_fgi_high_blocks_signal(self):
        """BTC bear + FGI>=40 → no signal (need Fear)."""
        for c in self.candles:
            c["symbol"] = "BTCUSDT"

        sig = self.gen.evaluate(self.candles, funding_z=-1.5, bull200=False, fgi=50)
        assert sig.type == SignalType.SIGNAL_FLAT
        assert "FGI" in sig.reason

    def test_btc_bull_pullback(self):
        """BTC: Bull pullback — V12 WidePullback range [-1.0, -0.2] → LONG."""
        for c in self.candles:
            c["symbol"] = "BTCUSDT"

        # Bull + z in [-1, -0.2] → pullback LONG
        sig = self.gen.evaluate(self.candles, funding_z=-0.5, bull200=True)
        assert sig.type == SignalType.SIGNAL_LONG
        assert "pullback" in sig.reason

        # Bull + z exactly at -0.2 boundary → no signal
        sig = self.gen.evaluate(self.candles, funding_z=-0.2, bull200=True)
        assert sig.type == SignalType.SIGNAL_FLAT

        # Bull + z at -0.3 → still in range (V12 widened to -0.2)
        sig = self.gen.evaluate(self.candles, funding_z=-0.3, bull200=True)
        assert sig.type == SignalType.SIGNAL_LONG

        # Bull + z > -0.2 → no pullback
        sig = self.gen.evaluate(self.candles, funding_z=-0.1, bull200=True)
        assert sig.type == SignalType.SIGNAL_FLAT

        # Bull + z < -1 → too extreme for bull pullback
        sig = self.gen.evaluate(self.candles, funding_z=-1.5, bull200=True)
        assert sig.type == SignalType.SIGNAL_FLAT
        assert "too extreme" in sig.reason

    def test_eth_bear_only_long(self):
        """ETH: z < -1 + bear regime → LONG; bull pullback works too."""
        for c in self.candles:
            c["symbol"] = "ETHUSDT"

        sig = self.gen.evaluate(self.candles, funding_z=-1.5, bull200=False)
        assert sig.type == SignalType.SIGNAL_LONG
        assert "ETH" in sig.reason

    def test_eth_bull_pullback(self):
        """ETH: Bull pullback — V12 WidePullback range [-1.0, -0.2] → LONG."""
        for c in self.candles:
            c["symbol"] = "ETHUSDT"

        # Bull + z in [-1, -0.2] → pullback LONG
        sig = self.gen.evaluate(self.candles, funding_z=-0.7, bull200=True)
        assert sig.type == SignalType.SIGNAL_LONG
        assert "pullback" in sig.reason

        # Bull + z at -0.3 → still in range (V12 widened to -0.2)
        sig = self.gen.evaluate(self.candles, funding_z=-0.3, bull200=True)
        assert sig.type == SignalType.SIGNAL_LONG

        # Bull + z at -0.2 boundary → no signal
        sig = self.gen.evaluate(self.candles, funding_z=-0.2, bull200=True)
        assert sig.type == SignalType.SIGNAL_FLAT

        # Bull + z < -1 → too extreme for bull
        sig = self.gen.evaluate(self.candles, funding_z=-1.5, bull200=True)
        assert sig.type == SignalType.SIGNAL_FLAT
        assert "too extreme" in sig.reason

    def test_doge_no_signal(self):
        """DOGE: Archived — failed WF Gate, no V2 signal."""
        for c in self.candles:
            c["symbol"] = "DOGEUSDT"
        sig = self.gen.evaluate(self.candles, funding_z=-1.5, bull200=False)
        assert sig.type == SignalType.SIGNAL_FLAT
        assert "no V2 signal" in sig.reason

    def test_sol_mild_negative_long(self):
        """SOL: z∈[-0.5, 0) + bull200 → LONG (V13b champion). Extended: z<-0.5 + bull200 also LONG."""
        for c in self.candles:
            c["symbol"] = "SOLUSDT"

        # z∈[-0.5, 0) + bull200 → LONG (V13b champion)
        sig = self.gen.evaluate(self.candles, funding_z=-0.3, bull200=True)
        assert sig.type == SignalType.SIGNAL_LONG
        assert "SOL" in sig.reason

        # z < -0.5 + bull200 → LONG (extended)
        sig = self.gen.evaluate(self.candles, funding_z=-1.3, bull200=True)
        assert sig.type == SignalType.SIGNAL_LONG
        assert "SOL" in sig.reason

        # z < -0.5 but bear → no signal (need bull regime)
        sig = self.gen.evaluate(self.candles, funding_z=-1.3, bull200=False)
        assert sig.type == SignalType.SIGNAL_FLAT

        # z > 0 → no signal
        sig = self.gen.evaluate(self.candles, funding_z=0.5, bull200=True)
        assert sig.type == SignalType.SIGNAL_FLAT

        # z ∈ [-0.5, 0) but bear → no signal
        sig = self.gen.evaluate(self.candles, funding_z=-0.3, bull200=False)
        assert sig.type == SignalType.SIGNAL_FLAT

    def test_no_funding_data(self):
        """No funding data → FLAT signal."""
        sig = self.gen.evaluate(self.candles, funding_z=None, bull200=True)
        assert sig.type == SignalType.SIGNAL_FLAT
        assert "No signal data" in sig.reason or "No funding" in sig.reason

    def test_other_assets_no_signal(self):
        """AVAX, DOGE, ADA → no V2 signal."""
        for asset in ["AVAXUSDT", "DOGEUSDT", "ADAUSDT"]:
            for c in self.candles:
                c["symbol"] = asset
            sig = self.gen.evaluate(self.candles, funding_z=-2.0, bull200=False)
            assert sig.type == SignalType.SIGNAL_FLAT
            assert "no V2 signal" in sig.reason

    def test_not_enough_candles(self):
        """< 210 candles → None."""
        sig = self.gen.evaluate(self.candles[:100], funding_z=-2.0)
        assert sig is None


class TestSignalGeneratorV2Exit:
    """Test exit logic with regime-dependent SL."""

    def setup_method(self):
        self.gen = SignalGeneratorV2()

    def test_trailing_disabled(self):
        """Trailing stop is disabled (p=0)."""
        pos = {"entry_price": 25.0, "peak_price": 26.0, "symbol": "AVAXUSDT", "side": "LONG"}
        # 3% below peak = 25.22, but trailing is disabled
        candle = {"low": 25.22, "high": 25.5, "close": 25.3, "timestamp": 1234}
        sig = self.gen.check_exit(pos, candle, bars_held=5, bull200=True)
        assert sig is None  # No trailing exit

    def test_no_trailing_stop_long(self):
        """LONG: price above trailing stop → no exit."""
        pos = {"entry_price": 25.0, "peak_price": 26.0, "symbol": "AVAXUSDT", "side": "LONG"}
        candle = {"low": 25.5, "high": 26.0, "close": 25.8, "timestamp": 1234}
        sig = self.gen.check_exit(pos, candle, bars_held=5, bull200=True)
        assert sig is None

    def test_emergency_stop_loss(self):
        """LONG: Emergency SL 4%."""
        pos = {"entry_price": 25.0, "peak_price": 25.0, "symbol": "AVAXUSDT", "side": "LONG"}
        candle = {"low": 23.9, "high": 24.8, "close": 24.0, "timestamp": 1234}
        # entry * 0.96 = 24.0
        sig = self.gen.check_exit(pos, candle, bars_held=5, bull200=True)
        assert sig is not None
        assert sig.type == SignalType.EXIT_STOP_LOSS
        assert "4.0%" in sig.reason

    def test_no_stop_loss_above_4pct(self):
        """LONG: No SL when drop < 4%."""
        pos = {"entry_price": 25.0, "peak_price": 25.0, "symbol": "AVAXUSDT", "side": "LONG"}
        candle = {"low": 24.2, "high": 24.5, "close": 24.3, "timestamp": 1234}
        # 24.2/25 = 3.2% drop, less than 4%
        sig = self.gen.check_exit(pos, candle, bars_held=5, bull200=True)
        assert sig is None

    def test_max_hold_24h(self):
        """Max hold 24 bars → exit."""
        pos = {"entry_price": 25.0, "peak_price": 26.0, "symbol": "AVAXUSDT", "side": "LONG"}
        candle = {"low": 25.5, "high": 26.0, "close": 25.8, "timestamp": 1234}
        sig = self.gen.check_exit(pos, candle, bars_held=24, bull200=True)
        assert sig is not None
        assert sig.type == SignalType.EXIT_MAX_HOLD
        assert "funding decay" in sig.reason

    def test_no_exit_before_max_hold(self):
        """bars_held < 24 → no max hold exit."""
        pos = {"entry_price": 25.0, "peak_price": 26.0, "symbol": "AVAXUSDT", "side": "LONG"}
        candle = {"low": 25.5, "high": 26.0, "close": 25.8, "timestamp": 1234}
        sig = self.gen.check_exit(pos, candle, bars_held=23, bull200=True)
        assert sig is None

    def test_short_emergency_sl(self):
        """SHORT: Emergency SL 4% above entry."""
        pos = {"entry_price": 25.0, "trough_price": 24.0, "symbol": "SOLUSDT", "side": "SHORT"}
        candle = {"low": 23.5, "high": 26.01, "close": 25.5, "timestamp": 1234}
        # entry * 1.04 = 26.0 → high=26.01 should trigger
        sig = self.gen.check_exit(pos, candle, bars_held=5, bull200=False)
        assert sig is not None
        assert sig.type == SignalType.EXIT_STOP_LOSS

    def test_regime_sl_method(self):
        """get_stop_loss_pct returns 4% (regime-independent)."""
        assert self.gen.get_stop_loss_pct() == 4.0


class TestSignalGeneratorV2Params:
    """Test custom parameters."""

    def test_custom_threshold(self):
        """Custom funding z threshold (SOL uses fixed -1.5, BTC/ETH use threshold)."""
        gen = SignalGeneratorV2(params={"funding_z_long_threshold": -0.5})
        candles = []
        for i in range(250):
            candles.append({
                "timestamp": 1700000000000 + i * 3600000,
                "open": 25 + i * 0.01, "high": 25.5 + i * 0.01,
                "low": 24.5 + i * 0.01, "close": 25 + i * 0.01,
                "volume": 1000, "symbol": "BTCUSDT",
            })
        # BTC bear+FGI<40 with z=-0.7 < -0.5 → LONG
        sig = gen.evaluate(candles, funding_z=-0.7, bull200=False, fgi=30)
        assert sig.type == SignalType.SIGNAL_LONG  # -0.7 < -0.5


class TestSignalGeneratorV2V14:
    """Test V14 extended signals (OI Surge, LS Ratio, Taker)."""

    def setup_method(self):
        self.gen = SignalGeneratorV2()
        self.candles = []
        for i in range(250):
            self.candles.append({
                "timestamp": 1700000000000 + i * 3600000,
                "open": 25 + i * 0.01, "high": 25.5 + i * 0.01,
                "low": 24.5 + i * 0.01, "close": 25 + i * 0.01,
                "volume": 1000, "symbol": "SOLUSDT",
            })

    def test_oi_surge_long(self):
        """OI surge >3% + bull200 → LONG (V14)."""
        sig = self.gen.evaluate(self.candles, oi_pct_change=5.0, bull200=True)
        assert sig.type == SignalType.SIGNAL_LONG
        assert "OI surge" in sig.reason
        assert "V14" in sig.reason

    def test_oi_surge_bear_skip(self):
        """OI surge >3% but bear → skip (not 2x threshold)."""
        sig = self.gen.evaluate(self.candles, oi_pct_change=4.0, bull200=False)
        assert sig.type == SignalType.SIGNAL_FLAT

    def test_oi_surge_bear_2x_long(self):
        """OI surge >6% (2x threshold) even in bear → LONG (V14)."""
        sig = self.gen.evaluate(self.candles, oi_pct_change=7.0, bull200=False)
        assert sig.type == SignalType.SIGNAL_LONG
        assert "2x threshold" in sig.reason

    def test_ls_ratio_short(self):
        """LS ratio >5 → SHORT (V14)."""
        sig = self.gen.evaluate(self.candles, ls_ratio=6.0, bull200=True)
        assert sig.type == SignalType.SIGNAL_SHORT
        assert "LS ratio" in sig.reason

    def test_ls_ratio_below_threshold(self):
        """LS ratio <5 → no V14 signal, falls through to funding logic."""
        sig = self.gen.evaluate(self.candles, ls_ratio=3.0, funding_z=-0.3, bull200=True)
        # Should fall through to SOL funding logic
        assert sig.type != SignalType.SIGNAL_SHORT

    def test_taker_buy_pressure_long(self):
        """Taker vol ratio >2 + bull200 → LONG (V14 experimental)."""
        sig = self.gen.evaluate(self.candles, taker_vol_ratio=2.5, bull200=True)
        assert sig.type == SignalType.SIGNAL_LONG
        assert "Taker buy" in sig.reason

    def test_taker_buy_pressure_bear_skip(self):
        """Taker vol ratio >2 but bear → skip."""
        sig = self.gen.evaluate(self.candles, taker_vol_ratio=2.5, bull200=False)
        assert sig.type == SignalType.SIGNAL_FLAT

    def test_v14_priority_over_funding(self):
        """V14 signals fire before funding logic (OI surge takes priority)."""
        # Both OI surge and funding_z trigger → OI surge wins
        sig = self.gen.evaluate(self.candles, oi_pct_change=5.0, funding_z=-0.3, bull200=True)
        assert sig.type == SignalType.SIGNAL_LONG
        assert "OI surge" in sig.reason

    def test_no_v14_data_falls_to_funding(self):
        """No V14 data → falls through to funding logic."""
        sig = self.gen.evaluate(self.candles, funding_z=-0.3, bull200=True)
        # SOL: z∈[-0.5, 0) + bull200 → LONG
        assert sig.type == SignalType.SIGNAL_LONG
        assert "V13b" in sig.reason or "V14" not in sig.reason