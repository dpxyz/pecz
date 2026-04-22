"""
Executor V1 — Signal Generator
Deterministic: same logic as backtest, no LLM, no ambiguity.
Entry: macd_hist > 0 AND close > ema_50 AND ema_50 > ema_200 AND adx_14 > 20
Exit:  trailing_stop 2%, stop_loss 2.5%, max_hold 48 bars
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import polars as pl

log = logging.getLogger("signal_generator")

# ── Indicator calculations (Polars Expression API) ──

def calc_ema(series: pl.Series, period: int) -> pl.Series:
    """EMA via exponential weighted mean.
    
    Note: Previous version used rolling_mean (SMA). This is now proper EMA
    using Polars ewm_mean with alpha = 2/(period+1).
    """
    return series.ewm_mean(alpha=2/(period+1), min_samples=period)


def calc_macd(closes: pl.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD using proper EMA (not SMA approximation)."""
    ema_fast = closes.ewm_mean(alpha=2/(fast+1), min_samples=fast)
    ema_slow = closes.ewm_mean(alpha=2/(slow+1), min_samples=slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm_mean(alpha=2/(signal+1), min_samples=signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_adx(df: pl.DataFrame, period: int = 14) -> pl.Series:
    """ADX — pure Polars Expression API (same as dsl_translator v3)."""
    high = pl.col("high")
    low = pl.col("low")
    close = pl.col("close")

    tr = pl.max_horizontal(
        (high - low),
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    )

    plus_dm = (
        pl.when((high - high.shift(1)) > (low.shift(1) - low))
        .then(pl.max_horizontal(high - high.shift(1), 0))
        .otherwise(0)
    )
    minus_dm = (
        pl.when((low.shift(1) - low) > (high - high.shift(1)))
        .then(pl.max_horizontal(low.shift(1) - low, 0))
        .otherwise(0)
    )

    atr_expr = tr.rolling_mean(window_size=period, min_samples=period)
    plus_di = 100 * (plus_dm.rolling_mean(window_size=period, min_samples=period) / atr_expr)
    minus_di = 100 * (minus_dm.rolling_mean(window_size=period, min_samples=period) / atr_expr)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    adx_expr = dx.rolling_mean(window_size=period, min_samples=period)

    result = df.select(adx_expr.alias("adx"))
    return result["adx"]


# ── Signal Types ──

class SignalType(Enum):
    SIGNAL_LONG = "SIGNAL_LONG"
    SIGNAL_FLAT = "SIGNAL_FLAT"
    EXIT_TRAILING = "EXIT_TRAILING"
    EXIT_STOP_LOSS = "EXIT_STOP_LOSS"
    EXIT_MAX_HOLD = "EXIT_MAX_HOLD"


@dataclass
class Signal:
    type: SignalType
    symbol: str
    timestamp: int
    price: float
    indicators: dict = field(default_factory=dict)
    reason: str = ""


# ── Strategy Parameters (from BASELINE_STRATEGY.md) ──

STRATEGY_PARAMS = {
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "ema_fast": 50,
    "ema_slow": 200,
    "adx_period": 14,
    "adx_threshold": 20,
    "trailing_stop_pct": 2.0,
    "stop_loss_pct": 2.5,
    "max_hold_bars": 48,
}


class SignalGenerator:
    """Deterministic signal generator — exact same logic as backtest."""

    def __init__(self, params: dict = None):
        self.p = {**STRATEGY_PARAMS, **(params or {})}
        log.info(f"SignalGenerator initialized: ADX>{self.p['adx_threshold']} "
                 f"EMA{self.p['ema_fast']}>EMA{self.p['ema_slow']} "
                 f"TS={self.p['trailing_stop_pct']}% SL={self.p['stop_loss_pct']}% "
                 f"MaxHold={self.p['max_hold_bars']}h")

    def evaluate(self, candles: list[dict]) -> Optional[Signal]:
        """
        Evaluate the latest candle against the strategy.
        Returns a Signal if action needed, None otherwise.
        candles: list of dicts with keys: timestamp, open, high, low, close, volume
        Must have >= 200 candles for EMA200 warmup.
        """
        if len(candles) < self.p["ema_slow"] + 10:
            log.warning(f"Not enough candles for evaluation: {len(candles)} < {self.p['ema_slow'] + 10}")
            return None

        # Build Polars DataFrame
        df = pl.DataFrame({
            "timestamp": [c["timestamp"] for c in candles],
            "open": [c["open"] for c in candles],
            "high": [c["high"] for c in candles],
            "low": [c["low"] for c in candles],
            "close": [c["close"] for c in candles],
            "volume": [c.get("volume", 0) for c in candles],
        })

        # Calculate indicators
        closes = df["close"]
        ema_50 = calc_ema(closes, self.p["ema_fast"])
        ema_200 = calc_ema(closes, self.p["ema_slow"])
        macd_line, macd_signal, macd_hist = calc_macd(
            closes, self.p["macd_fast"], self.p["macd_slow"], self.p["macd_signal"]
        )
        adx = calc_adx(df, self.p["adx_period"])

        # Last values
        n = len(df) - 1
        current_close = closes[n]
        current_ema50 = ema_50[n]
        current_ema200 = ema_200[n]
        current_macd_hist = macd_hist[n]
        current_adx = adx[n] if adx[n] is not None else 0

        indicators = {
            "close": current_close,
            "ema_50": round(current_ema50, 2) if current_ema50 else None,
            "ema_200": round(current_ema200, 2) if current_ema200 else None,
            "macd_hist": round(current_macd_hist, 4) if current_macd_hist else None,
            "adx_14": round(current_adx, 2) if current_adx else None,
        }

        # ── Entry Logic ──
        entry_condition = (
            current_macd_hist is not None and current_macd_hist > 0
            and current_close is not None and current_ema50 is not None
            and current_close > current_ema50
            and current_ema50 is not None and current_ema200 is not None
            and current_ema50 > current_ema200
            and current_adx is not None and current_adx > self.p["adx_threshold"]
        )

        last_candle = candles[-1]
        symbol = last_candle.get("symbol", "UNKNOWN")
        ts = last_candle["timestamp"]

        if entry_condition:
            return Signal(
                type=SignalType.SIGNAL_LONG,
                symbol=symbol,
                timestamp=ts,
                price=current_close,
                indicators=indicators,
                reason=f"macd_hist={current_macd_hist:.4f} > 0, "
                       f"close={current_close:.2f} > ema50={current_ema50:.2f}, "
                       f"ema50 > ema200={current_ema200:.2f}, "
                       f"adx={current_adx:.1f} > {self.p['adx_threshold']}",
            )

        return Signal(
            type=SignalType.SIGNAL_FLAT,
            symbol=symbol,
            timestamp=ts,
            price=current_close,
            indicators=indicators,
            reason=f"No entry: macd_hist={current_macd_hist:.4f}, "
                   f"close vs ema50: {current_close:.2f}/{current_ema50:.2f}, "
                   f"ema50 vs ema200: {current_ema50:.2f}/{current_ema200:.2f}, "
                   f"adx={current_adx:.1f}/{self.p['adx_threshold']}",
        )

    def check_exit(self, position: dict, current_candle: dict, bars_held: int) -> Optional[Signal]:
        """Check if current position should exit."""
        entry_price = position["entry_price"]
        high = current_candle["high"]
        low = current_candle["low"]
        close = current_candle["close"]
        symbol = position["symbol"]
        ts = current_candle["timestamp"]

        # Trailing stop: 2% below peak
        peak = position.get("peak_price", entry_price)
        trailing_stop = peak * (1 - self.p["trailing_stop_pct"] / 100)

        if low <= trailing_stop:
            return Signal(
                type=SignalType.EXIT_TRAILING,
                symbol=symbol, timestamp=ts, price=trailing_stop,
                reason=f"Trailing stop hit: low={low:.2f} <= stop={trailing_stop:.2f} "
                       f"(peak={peak:.2f}, -{self.p['trailing_stop_pct']}%)",
            )

        # Stop loss: 2.5% below entry
        stop_loss = entry_price * (1 - self.p["stop_loss_pct"] / 100)
        if low <= stop_loss:
            return Signal(
                type=SignalType.EXIT_STOP_LOSS,
                symbol=symbol, timestamp=ts, price=stop_loss,
                reason=f"Stop loss hit: low={low:.2f} <= sl={stop_loss:.2f} "
                       f"(entry={entry_price:.2f}, -{self.p['stop_loss_pct']}%)",
            )

        # Max hold: 48 bars
        if bars_held >= self.p["max_hold_bars"]:
            return Signal(
                type=SignalType.EXIT_MAX_HOLD,
                symbol=symbol, timestamp=ts, price=close,
                reason=f"Max hold reached: {bars_held}h >= {self.p['max_hold_bars']}h",
            )

        return None


# ── Standalone test with historical data ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")

    # Load BTC data from Foundry
    data_dir = Path("/data/.openclaw/workspace/forward_v5/forward_v5/research/data")
    df = pl.read_parquet(str(data_dir / "BTCUSDT_1h_full.parquet"))

    # Convert to candle dicts
    candles = []
    for row in df.iter_rows(named=True):
        candles.append({
            "timestamp": row["timestamp"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row.get("volume", 0),
            "symbol": "BTCUSDT",
        })

    gen = SignalGenerator()

    # Sliding window: simulate live evaluation
    window_size = 210  # 200 for EMA200 + 10 buffer
    signals_long = 0
    signals_flat = 0

    print(f"Testing SignalGenerator on {len(candles)} BTC candles...")
    for i in range(window_size, len(candles), 24):  # Every 24h
        window = candles[i - window_size:i]
        signal = gen.evaluate(window)
        if signal and signal.type == SignalType.SIGNAL_LONG:
            signals_long += 1
        else:
            signals_flat += 1

    total = signals_long + signals_flat
    print(f"\nResult: {signals_long} LONG signals, {signals_flat} FLAT signals "
          f"({signals_long/max(total,1)*100:.1f}% long)")
    print("✅ SignalGenerator works with historical data")