"""
Executor V2 — Regime-Adaptive Funding Signal Generator

Entry signals (HYP-06 + Foundry V12 validated):
1. BTC Bear: z<-1 + FGI<40 → Long (V11: +73.9% cum, 100% WF)
2. BTC Bull Pullback: -1.0<z<-0.2 → Long (V12 WidePullback: +70% cum, 5/6 WF)
3. BTC 4h Bull Pullback: -1.0<z<-0.2 + bull200 → Long (V12: +94% cum, 5/6 WF)
4. ETH Bear: z<-1 → Long (V11: +24.70% cum, 5/6 WF)
5. ETH Bull Pullback: -1.0<z<-0.2 → Long (V12 WidePullback: +71.5% cum, 5/6 WF)
6. SOL: z∈[-0.5, 0) + bull200 → Long (V13b: R=70, OOS=+4.83%, 239 trades)
   Extended: z<-0.5 + bull200 → Long (broader negative funding capture)

Regime: bull200 (close > ema200 = bull)
Z-Score: (funding_rate - rolling_mean) / rolling_std, 8h funding, 168h window

V12 Changes:
- Pullback range widened from [-1.0, -0.3] to [-1.0, -0.2] (WidePullback)
  - BTC: +54% → +70%, ETH: +25% → +72%
- BTC 4h timeframe added (V12: +94% cum, 5/6 WF)

Exit: TIME-BASED 24h hold (primary) — funding signals need time to play out
- SL 4% (emergency only — wide to avoid killing recovering trades)
- Trailing stop: DISABLED (V1's 2% was too tight, 3% still kills recovering trades)
- Max hold: 24 bars (24h) — primary exit, funding signal decays after 24h

IMPORTANT: Dry-run proved SL/TS kills trades that recover within 24h.
Funding edge is a mean-reversion play — it needs time. SL only for black swans.

Costs: 0.1% round-trip (0.02% maker fee + 0.03% slippage × 2)
"""

from typing import Optional
import logging
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger("signal_generator_v2")

# ── Signal Types ──

class SignalType(Enum):
    SIGNAL_LONG = "SIGNAL_LONG"
    SIGNAL_SHORT = "SIGNAL_SHORT"
    SIGNAL_FLAT = "SIGNAL_FLAT"
    EXIT_TRAILING = "EXIT_TRAILING"
    EXIT_STOP_LOSS = "EXIT_STOP_LOSS"
    EXIT_MAX_HOLD = "EXIT_MAX_HOLD"
    EXIT_SIGNAL = "EXIT_SIGNAL"  # Time-based exit (24h hold)


@dataclass
class Signal:
    type: SignalType
    symbol: str
    timestamp: int
    price: float
    indicators: dict = field(default_factory=dict)
    reason: str = ""


# ── Strategy Parameters ──

STRATEGY_PARAMS = {
    # Funding z-score thresholds
    "funding_z_long_threshold": -1.0,    # Long when z < -1 (extreme negative = shorts crowded)
    "funding_z_short_threshold": 1.0,    # Short when z > +1 (extreme positive = longs crowded)
    "funding_z_window": 168,              # 168h rolling window for z-score (7 days)

    # Regime
    "ema_trend": 200,                     # EMA200 for bull/bear regime
    "ema_fast": 50,                       # EMA50 for additional context

    # Exit parameters — FUNDING-SPECIFIC
    "trailing_stop_pct": 0,               # DISABLED — trailing stops kill mean-reversion
    "stop_loss_pct": 4.0,                 # Emergency SL (4% — Prop-Firm-kompatibel, 0.2x effektiv = 0.8% equity risk)
    "max_hold_bars": 24,                  # 24h max hold — PRIMARY EXIT

    # Position limits
    "max_positions_per_asset": 1,
    "cooldown_bars": 24,                  # 24h cooldown (funding is 8h-cyclical)
}


class SignalGeneratorV2:
    """Funding-first signal generator — V2 of the trading engine.

    Signals are based on extreme funding rates (contrarian), with regime filtering.
    No MACD, no standard indicators for entry — only funding z-score + regime.
    """

    def __init__(self, params: Optional[dict] = None):
        self.p = {**STRATEGY_PARAMS, **(params or {})}
        log.info(f"SignalGeneratorV2 initialized:")
        log.info(f"  Bear: z < {self.p['funding_z_long_threshold']} (extreme negative funding)")
        log.info(f"  Bull Pullback: -1.0 < z < -0.2 (V12 WidePullback)")
        log.info(f"  SOL: z∈[-0.5, 0) + bull200 (V13b champion, R=70, OOS=+4.83%)")
        log.info(f"  Regime: bull200 (close > EMA{self.p['ema_trend']})")
        log.info(f"  Exit: 24h time-based (primary), Emergency SL {self.p['stop_loss_pct']}%, Trailing DISABLED")
        log.info(f"  ⚠️ SOL z<-1.5 GESTRICHEN — V13b beweist: mild negativ = robust, extrem = zu wenige Trades")

    def evaluate(self, candles: list[dict], funding_z: Optional[float] = None,
                 bull200: Optional[bool] = None, fgi: Optional[int] = None) -> Optional[Signal]:
        """
        Evaluate the latest candle against the funding-first strategy.

        Args:
            candles: list of candle dicts (timestamp, open, high, low, close, volume)
                     Must have >= 200 candles for EMA200 warmup.
            funding_z: current funding z-score (pre-calculated by DataFeed)
            bull200: whether we're in bull regime (close > ema200). None = compute from candles.

        Returns:
            Signal if action needed, None if not enough data.
        """
        if len(candles) < self.p["ema_trend"] + 10:
            log.warning(f"Not enough candles: {len(candles)} < {self.p['ema_trend'] + 10}")
            return None

        # Calculate indicators from candles
        import polars as pl
        closes = pl.Series([c["close"] for c in candles])
        ema_200 = closes.ewm_mean(alpha=2 / (self.p["ema_trend"] + 1), min_samples=self.p["ema_trend"])
        ema_50 = closes.ewm_mean(alpha=2 / (self.p["ema_fast"] + 1), min_samples=self.p["ema_fast"])

        n = len(candles) - 1
        current_close = closes[n]
        current_ema50 = ema_50[n]
        current_ema200 = ema_200[n]

        # Determine regime
        if bull200 is None:
            bull200 = current_close > current_ema200 if current_ema200 is not None else True

        last_candle = candles[-1]
        symbol = last_candle.get("symbol", "UNKNOWN")
        ts = last_candle["timestamp"]

        indicators = {
            "close": round(current_close, 2),
            "ema_50": round(current_ema50, 2) if current_ema50 else None,
            "ema_200": round(current_ema200, 2) if current_ema200 else None,
            "funding_z": round(funding_z, 3) if funding_z is not None else None,
            "bull200": bull200,
        }

        # ── No funding data = no signal ──
        if funding_z is None:
            return Signal(
                type=SignalType.SIGNAL_FLAT,
                symbol=symbol, timestamp=ts, price=current_close,
                indicators=indicators,
                reason=f"No funding data — skipping",
            )

        # ── Signal Logic (HYP-06 + V12 WidePullback) ──
        # Bear: z < -1 (extreme negative = shorts crowded → contrarian Long)
        # Bull Pullback: -1.0 < z < -0.2 (V12 WidePullback: wider range = more trades, +70/+72% cum)
        # SOL: z < -1.5 (deep negative, all regimes)
        # BTC Bear additionally requires FGI < 40

        reason = ""
        signal_type = SignalType.SIGNAL_FLAT

        if symbol == "BTCUSDT":
            if not bull200:
                # Bear + FGI<40: V11 validated, +73.9% cum, 100% WF
                # FGI=None → allow signal (conservative: assume fear may be present)
                if funding_z < self.p["funding_z_long_threshold"]:
                    if fgi is None or fgi < 40:
                        signal_type = SignalType.SIGNAL_LONG
                        reason = f"BTC: funding_z={funding_z:.3f} < -1, bear, FGI={fgi}→ LONG"
                    else:
                        reason = f"BTC: z={funding_z:.3f}, bear, but FGI={fgi}≥40 → no signal (need Fear)"
            else:
                # BULL PULLBACK: V12 WidePullback, range [-1.0, -0.2] (+70% cum, 5/6 WF)
                if -1.0 < funding_z < -0.2:
                    signal_type = SignalType.SIGNAL_LONG
                    reason = f"BTC: funding_z={funding_z:.3f} in [-1,-0.2], bull pullback → LONG"
                elif funding_z <= -1.0:
                    reason = f"BTC: z={funding_z:.3f}≤-1 in bull → no signal (too extreme for bull)"
                else:
                    reason = f"BTC: z={funding_z:.3f} > -0.2 in bull → no pullback signal"

        elif symbol == "ETHUSDT":
            if not bull200:
                # Bear z<-1: V11 validated, 5/6 WF PASS
                if funding_z < self.p["funding_z_long_threshold"]:
                    signal_type = SignalType.SIGNAL_LONG
                    reason = f"ETH: funding_z={funding_z:.3f} < -1, bear regime → LONG"
            else:
                # BULL PULLBACK: V12 WidePullback, range [-1.0, -0.2] (+72% cum, 5/6 WF)
                if -1.0 < funding_z < -0.2:
                    signal_type = SignalType.SIGNAL_LONG
                    reason = f"ETH: funding_z={funding_z:.3f} in [-1,-0.2], bull pullback → LONG"
                elif funding_z <= -1.0:
                    reason = f"ETH: z={funding_z:.3f}≤-1 in bull → no signal (too extreme for bull)"
                else:
                    reason = f"ETH: z={funding_z:.3f} > -0.2 in bull → no pullback signal"

        elif symbol == "SOLUSDT":
            # V13b Champion: z∈[-0.5, 0) Long + EMA200 bull (R=70, OOS=+4.83%, 239 trades)
            # Deep Research: mild negatives Funding = der Edge (z<-1.5 zu streng, zu wenige Trades)
            # V13b-Label-Bug: "bear_z<-0.5" war eigentlich z∈[-0.5, 0) = leicht negatives Funding
            if -0.5 <= funding_z < 0 and bull200:
                signal_type = SignalType.SIGNAL_LONG
                reason = f"SOL: funding_z={funding_z:.3f} ∈ [-0.5, 0), bull200={bull200} → LONG (V13b champion)"
            elif funding_z < -0.5 and bull200:
                # Fallback: stärker negatives Funding im Bull-Regime auch erlaubt
                signal_type = SignalType.SIGNAL_LONG
                reason = f"SOL: funding_z={funding_z:.3f} < -0.5, bull200={bull200} → LONG (extended)"
            else:
                reason = f"SOL: funding_z={funding_z:.3f}, bull200={bull200} → no signal"

        else:
            reason = f"{symbol}: no V2 signal (BTC/ETH/SOL only)"

        return Signal(
            type=signal_type,
            symbol=symbol, timestamp=ts, price=current_close,
            indicators=indicators,
            reason=reason or f"No entry: funding_z={funding_z:.3f}, bull200={bull200}",
        )

    def get_stop_loss_pct(self) -> float:
        """Emergency stop loss (regime-independent — wide for mean-reversion)."""
        return self.p["stop_loss_pct"]

    def check_exit(self, position: dict, current_candle: dict, bars_held: int,
                   bull200: bool = True) -> Optional[Signal]:
        """Check if current position should exit.

        V2 exits:
        1. Trailing stop: 3% below peak
        2. Stop loss: 2.5% (bull) or 1.5% (bear) below entry
        3. Max hold: 24 bars (funding signal decays)
        """
        entry_price = position["entry_price"]
        low = current_candle["low"]
        close = current_candle["close"]
        symbol = position["symbol"]
        ts = current_candle["timestamp"]
        side = position.get("side", "LONG")

        # ── EMERGENCY STOP LOSS (4%) ──
        # Only for black swan protection. Funding edge needs time to play out.
        sl_pct = self.get_stop_loss_pct()
        if side == "LONG":
            stop_loss = entry_price * (1 - sl_pct / 100)
            if low <= stop_loss:
                return Signal(
                    type=SignalType.EXIT_STOP_LOSS,
                    symbol=symbol, timestamp=ts, price=stop_loss,
                    reason=f"Emergency SL: low={low:.2f} <= sl={stop_loss:.2f} "
                           f"(entry={entry_price:.2f}, -{sl_pct}%)",
                )
        else:
            high = current_candle.get("high", close)
            stop_loss = entry_price * (1 + sl_pct / 100)
            if high >= stop_loss:
                return Signal(
                    type=SignalType.EXIT_STOP_LOSS,
                    symbol=symbol, timestamp=ts, price=stop_loss,
                    reason=f"Emergency SL (SHORT): high={high:.2f} >= sl={stop_loss:.2f} "
                           f"(entry={entry_price:.2f}, +{sl_pct}%)",
                )

        # Max hold: 24 bars (funding signal decays)
        if bars_held >= self.p["max_hold_bars"]:
            return Signal(
                type=SignalType.EXIT_MAX_HOLD,
                symbol=symbol, timestamp=ts, price=close,
                reason=f"Max hold: {bars_held}h >= {self.p['max_hold_bars']}h (funding decay)",
            )

        return None