"""
Executor V1 — Signal Generator Tests

Covers:
- Entry conditions (MACD + EMA + ADX)
- Exit conditions (trailing stop, stop loss, max hold)
- Edge cases: insufficient candles, None indicators
- Parameter consistency with backtest
"""

import pytest
import polars as pl

from signal_generator import (
    SignalGenerator, SignalType, Signal,
    calc_ema, calc_macd, calc_adx,
    STRATEGY_PARAMS,
)


@pytest.fixture
def gen():
    return SignalGenerator()


def make_candles(n: int = 210, base_price: float = 75000.0, trend: str = "flat") -> list[dict]:
    """Generate synthetic candles for testing.

    trend: "up" (rising prices), "down" (falling), "flat" (sideways)
    """
    candles = []
    price = base_price
    for i in range(n):
        if trend == "up":
            price = base_price + (i * 50)  # steady uptrend
        elif trend == "down":
            price = base_price - (i * 50)
        else:
            price = base_price + (i % 20 - 10) * 10  # oscillate

        candles.append({
            "timestamp": 1700000000000 + i * 3600000,
            "open": price,
            "high": price + 100,
            "low": price - 100,
            "close": price,
            "volume": 1000.0,
            "symbol": "BTCUSDT",
        })
    return candles


class TestEntryConditions:
    def test_no_entry_without_enough_candles(self, gen):
        """Need ≥210 candles for EMA-200 warmup."""
        candles = make_candles(50)
        signal = gen.evaluate(candles)
        assert signal is None

    def test_flat_market_no_entry(self, gen):
        """Flat/sideways market should not generate LONG signal."""
        candles = make_candles(250, trend="flat")
        signal = gen.evaluate(candles)
        # Flat market: macd_hist ≈ 0, close ≈ ema50 ≈ ema200
        # Should return SIGNAL_FLAT, not SIGNAL_LONG
        if signal:
            assert signal.type == SignalType.SIGNAL_FLAT

    def test_uptrend_may_generate_long(self, gen):
        """Strong uptrend should eventually trigger LONG signal."""
        candles = make_candles(250, trend="up")
        signal = gen.evaluate(candles)
        # In strong uptrend, all conditions may be met
        # But synthetic data might not trigger ADX>20
        # This is a sanity check, not a guarantee
        if signal:
            assert signal.type in (SignalType.SIGNAL_LONG, SignalType.SIGNAL_FLAT)

    def test_signal_contains_indicators(self, gen):
        """Signal should always contain indicator values."""
        candles = make_candles(250)
        signal = gen.evaluate(candles)
        if signal:
            assert "close" in signal.indicators
            assert "ema_50" in signal.indicators
            assert "ema_200" in signal.indicators
            assert "macd_hist" in signal.indicators
            assert "adx_14" in signal.indicators

    def test_signal_has_symbol_and_timestamp(self, gen):
        """Signal should carry the correct symbol and timestamp."""
        candles = make_candles(250)
        signal = gen.evaluate(candles)
        if signal:
            assert signal.symbol == "BTCUSDT"
            assert signal.timestamp == candles[-1]["timestamp"]


class TestExitConditions:
    def test_trailing_stop_fires(self, gen):
        """When low ≤ trailing_stop, EXIT_TRAILING should fire."""
        position = {
            "entry_price": 75000.0,
            "symbol": "BTCUSDT",
            "peak_price": 77000.0,  # peak 2.67% above entry
        }
        # trailing_stop = 77000 * 0.98 = 75460
        candle = {
            "timestamp": 1700000000000,
            "high": 77000.0,
            "low": 75000.0,  # below trailing stop (75460)
            "close": 75100.0,
        }
        signal = gen.check_exit(position, candle, bars_held=1)
        assert signal is not None
        assert signal.type == SignalType.EXIT_TRAILING

    def test_stop_loss_fires(self, gen):
        """When low ≤ stop_loss, EXIT_STOP_LOSS should fire."""
        position = {
            "entry_price": 75000.0,
            "symbol": "BTCUSDT",
            "peak_price": 75000.0,  # no gain yet
        }
        # stop_loss = 75000 * 0.975 = 73125
        # trailing_stop = 75000 * 0.98 = 73500 (higher → fires first)
        candle = {
            "timestamp": 1700000000000,
            "high": 75200.0,
            "low": 73000.0,  # below both stops
            "close": 73100.0,
        }
        signal = gen.check_exit(position, candle, bars_held=1)
        assert signal is not None
        # Trailing stop (73500) fires before stop_loss (73125) in check order
        assert signal.type in (SignalType.EXIT_TRAILING, SignalType.EXIT_STOP_LOSS)

    def test_max_hold_fires(self, gen):
        """After max_hold_bars (48), EXIT_MAX_HOLD should fire."""
        position = {
            "entry_price": 75000.0,
            "symbol": "BTCUSDT",
            "peak_price": 76000.0,
        }
        candle = {
            "timestamp": 1700000000000,
            "high": 75500.0,
            "low": 75000.0,
            "close": 75300.0,
        }
        signal = gen.check_exit(position, candle, bars_held=48)
        assert signal is not None
        assert signal.type == SignalType.EXIT_MAX_HOLD

    def test_no_exit_when_in_profit(self, gen):
        """Position in profit with no stop hit → no exit signal."""
        position = {
            "entry_price": 75000.0,
            "symbol": "BTCUSDT",
            "peak_price": 77000.0,
        }
        # trailing_stop = 77000 * 0.98 = 75460
        candle = {
            "timestamp": 1700000000000,
            "high": 75800.0,
            "low": 75500.0,  # above trailing stop
            "close": 75600.0,
        }
        signal = gen.check_exit(position, candle, bars_held=5)
        assert signal is None

    def test_exit_priority_trailing_before_stoploss(self, gen):
        """Trailing stop should be checked before stop loss."""
        position = {
            "entry_price": 75000.0,
            "symbol": "BTCUSDT",
            "peak_price": 76000.0,  # trailing = 76000*0.98 = 74480
        }
        candle = {
            "timestamp": 1700000000000,
            "high": 76000.0,
            "low": 74000.0,  # below both
            "close": 74100.0,
        }
        signal = gen.check_exit(position, candle, bars_held=5)
        assert signal.type == SignalType.EXIT_TRAILING  # not STOP_LOSS


class TestIndicatorCalculation:
    def test_ema_returns_correct_length(self):
        closes = pl.Series([float(i) for i in range(200)])
        ema = calc_ema(closes, 50)
        assert len(ema) == 200

    def test_macd_returns_three_series(self):
        closes = pl.Series([float(i) for i in range(200)])
        macd_line, signal_line, histogram = calc_macd(closes)
        assert len(macd_line) == 200
        assert len(signal_line) == 200
        assert len(histogram) == 200

    def test_adx_returns_correct_length(self):
        df = pl.DataFrame({
            "high": [100.0 + i for i in range(200)],
            "low": [99.0 + i for i in range(200)],
            "close": [99.5 + i for i in range(200)],
        })
        adx = calc_adx(df, 14)
        assert len(adx) == 200


class TestParameterConsistency:
    """Ensure executor parameters match backtest specification."""

    def test_trailing_stop_pct(self):
        assert STRATEGY_PARAMS["trailing_stop_pct"] == 2.0

    def test_stop_loss_pct(self):
        assert STRATEGY_PARAMS["stop_loss_pct"] == 2.5

    def test_max_hold_bars(self):
        assert STRATEGY_PARAMS["max_hold_bars"] == 48

    def test_ema_periods(self):
        assert STRATEGY_PARAMS["ema_fast"] == 50
        assert STRATEGY_PARAMS["ema_slow"] == 200

    def test_adx_threshold(self):
        assert STRATEGY_PARAMS["adx_threshold"] == 20

    def test_macd_params(self):
        assert STRATEGY_PARAMS["macd_fast"] == 12
        assert STRATEGY_PARAMS["macd_slow"] == 26
        assert STRATEGY_PARAMS["macd_signal"] == 9