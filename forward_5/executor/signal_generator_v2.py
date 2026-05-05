"""
Executor V2 — Regime-Adaptive Funding + Extended Signal Generator

Entry signals:
  FUNDING-BASED (V12/V13 validated):
  1. BTC Bear: z<-1 + FGI<40 → Long (V11: +73.9% cum, 100% WF)
  2. BTC Bull Pullback: -1.0<z<-0.2 → Long (V12: +70% cum, 5/6 WF)
  3. BTC 4h Bull Pullback: -1.0<z<-0.2 + bull200 → Long (V12: +94% cum, 5/6 WF)
  4. ETH Bear: z<-1 → Long (V11: +24.70% cum, 5/6 WF)
  5. ETH Bull Pullback: -1.0<z<-0.2 → Long (V12: +71.5% cum, 5/6 WF)
  6. SOL: z∈[-0.5, 0) + bull200 → Long (V13b: R=70, OOS=+4.83%, 239 trades)

  EXTENDED-BASED (V14 validated, 2yr data):
  7. OI Surge SOL: ΔOI>3% + bull200 → Long (PBO=0.33, OOS=+66.6%)
  8. OI Surge BTC: ΔOI>3% + bull200 → Long (PBO=0.50, OOS=+68.2%)
  9. LS Ratio Short SOL: toptrader_ls>5 + bear → Short (PBO=0.33, OOS=+57.3%)
  10. Taker Buy Pressure: taker_vol>2.0 + bull200 → Long (PBO=0.40, experimental)

Regime: bull200 (close > ema200 = bull)
Z-Score: (funding_rate - rolling_mean) / rolling_std, 8h funding, 168h window

Exit: TIME-BASED 24h hold (primary), SL 4% (emergency), Trailing DISABLED
Costs: 0.1% round-trip
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

    # V14: Extended feature thresholds (CPCV-validated)
    "oi_surge_threshold": 3.0,            # ΔOI > 3% = OI surge (PBO=0.33)
    "ls_ratio_short_threshold": 5.0,      # TopTrader LS > 5 = contrarian short (PBO=0.33)
    "taker_buy_threshold": 2.0,            # Taker buy ratio > 2 = buy pressure (experimental)
    "dxy_weak_threshold": -2.0,           # DXY 10d ROC < -2% = weak dollar (confluence only)
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
                 bull200: Optional[bool] = None, fgi: Optional[int] = None,
                 oi_pct_change: Optional[float] = None,
                 ls_ratio: Optional[float] = None,
                 taker_vol_ratio: Optional[float] = None,
                 dxy_10d_roc: Optional[float] = None,
                 crosssec_z: Optional[float] = None) -> Optional[Signal]:
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
            "oi_pct_change": round(oi_pct_change, 2) if oi_pct_change is not None else None,
            "ls_ratio": round(ls_ratio, 2) if ls_ratio is not None else None,
            "taker_vol_ratio": round(taker_vol_ratio, 2) if taker_vol_ratio is not None else None,
            "dxy_10d_roc": round(dxy_10d_roc, 2) if dxy_10d_roc is not None else None,
            "crosssec_z": round(crosssec_z, 3) if crosssec_z is not None else None,
        }

        # ── Signal Logic ──
        # Priority: V14 extended signals (OI, LS, Taker) first, then funding-based
        reason = ""
        signal_type = SignalType.SIGNAL_FLAT
        v14_signal = False

        # ── DXY Confluence Filter ──
        # DXY 10d ROC < -2% = weak dollar → boosts LONG confidence (DR: 94% BTC win rate)
        # Not a standalone signal, but a gate: if DXY is STRONG (+2%), skip LONGs
        dxy_confluence = None
        if dxy_10d_roc is not None:
            if dxy_10d_roc < self.p["dxy_weak_threshold"]:
                dxy_confluence = "boost"   # weak dollar → better for longs
            elif dxy_10d_roc > abs(self.p["dxy_weak_threshold"]):
                dxy_confluence = "headwind"  # strong dollar → worse for longs
            else:
                dxy_confluence = "neutral"

        # ── FGI Confluence Filter ──
        # FGI < 40 = extreme fear → confluence for LONGs (DR: use as filter, not entry)
        fgi_fear = fgi is not None and fgi < 40
        fgi_greed = fgi is not None and fgi >= 75  # extreme greed → caution


        # V14: OI Surge: ΔOI > threshold + bull200 → Long (PBO=0.33)
        if oi_pct_change is not None and oi_pct_change > self.p["oi_surge_threshold"]:
            if bull200:
                # DXY headwind → skip OI surge longs (strong dollar = macro headwind)
                if dxy_confluence == "headwind":
                    reason = f"{symbol}: OI surge {oi_pct_change:+.1f}% but DXY strong ({dxy_10d_roc:+.1f}%) → skip"
                else:
                    signal_type = SignalType.SIGNAL_LONG
                    dxy_tag = " 📉weakDXY" if dxy_confluence == "boost" else ""
                    reason = f"{symbol}: OI surge {oi_pct_change:+.1f}% > {self.p['oi_surge_threshold']}%, bull200{dxy_tag} → LONG (V14)"
                    v14_signal = True
            elif oi_pct_change > self.p["oi_surge_threshold"] * 2:
                # 2x threshold overrides DXY headwind
                signal_type = SignalType.SIGNAL_LONG
                reason = f"{symbol}: OI surge {oi_pct_change:+.1f}% > {self.p['oi_surge_threshold']*2}% (2x threshold), bear → LONG (V14)"
                v14_signal = True
            else:
                reason = f"{symbol}: OI surge {oi_pct_change:+.1f}% but bear regime → skip"
        
        # V14: LS Ratio Short: toptrader_ls > threshold → Short (PBO=0.33)
        # DXY boost/headwind applies inversely for shorts
        elif ls_ratio is not None and ls_ratio > self.p["ls_ratio_short_threshold"]:
            if dxy_confluence == "boost":
                # Weak dollar = headwind for shorts
                reason = f"{symbol}: LS ratio {ls_ratio:.1f} > {self.p['ls_ratio_short_threshold']} but DXY weak ({dxy_10d_roc:+.1f}%) → skip short"
            else:
                signal_type = SignalType.SIGNAL_SHORT
                reason = f"{symbol}: LS ratio {ls_ratio:.1f} > {self.p['ls_ratio_short_threshold']}, contrarian SHORT (V14)"
                v14_signal = True
        
        # V14: Taker Buy Pressure: taker_vol > threshold + bull200 → Long (experimental)
        elif taker_vol_ratio is not None and taker_vol_ratio > self.p["taker_buy_threshold"]:
            if bull200:
                if dxy_confluence == "headwind":
                    reason = f"{symbol}: Taker buy {taker_vol_ratio:.1f} but DXY strong ({dxy_10d_roc:+.1f}%) → skip"
                else:
                    signal_type = SignalType.SIGNAL_LONG
                    reason = f"{symbol}: Taker buy {taker_vol_ratio:.1f} > {self.p['taker_buy_threshold']}, bull200 → LONG (V14 exp)"
                    v14_signal = True
            else:
                reason = f"{symbol}: Taker buy {taker_vol_ratio:.1f} but bear → skip"
        
        # V13: Cross-sectional Funding z<-1.0 + bull200 → Long (PBO=0.20, ρ=0.02)
        # Asset is unusually shorted relative to peers → contrarian long
        elif crosssec_z is not None and crosssec_z < -1.0:
            v14_signal = True  # Mark as V14 so funding path is skipped
            if bull200:
                if dxy_confluence == "headwind":
                    reason = f"{symbol}: crosssec_z={crosssec_z:.2f} < -1, bull200 but DXY strong ({dxy_10d_roc:+.1f}%) → skip"
                else:
                    signal_type = SignalType.SIGNAL_LONG
                    dxy_tag = " 📉weakDXY" if dxy_confluence == "boost" else ""
                    reason = f"{symbol}: crosssec_z={crosssec_z:.2f} < -1, bull200{dxy_tag} → LONG (crosssec)"
            else:
                reason = f"{symbol}: crosssec_z={crosssec_z:.2f} < -1 but bear → skip"
        
        # ── Funding-based signals (V12/V13 validated) ──
        # Only if no V14 signal fired AND we have funding data
        if not v14_signal and signal_type == SignalType.SIGNAL_FLAT:
            if funding_z is None:
                # If we have a reason (e.g. DXY filtered a V14 signal), return it
                if reason:
                    return Signal(
                        type=SignalType.SIGNAL_FLAT,
                        symbol=symbol, timestamp=ts, price=current_close,
                        indicators=indicators,
                        reason=reason,
                    )
                return Signal(
                    type=SignalType.SIGNAL_FLAT,
                    symbol=symbol, timestamp=ts, price=current_close,
                    indicators=indicators,
                    reason=f"No signal data — skipping",
                )

            # BTC: Bear z<-1 + FGI<40, Bull Pullback z∈[-1,-0.2]
            if symbol == "BTCUSDT":
                if not bull200:
                    if funding_z < self.p["funding_z_long_threshold"]:
                        if fgi is None or fgi < 40:
                            # DXY check for BTC bear longs
                            if dxy_confluence == "headwind":
                                reason = f"BTC: z={funding_z:.3f}, bear, FGI={fgi} but DXY strong ({dxy_10d_roc:+.1f}%) → skip"
                            else:
                                signal_type = SignalType.SIGNAL_LONG
                                dxy_tag = " 📉weakDXY" if dxy_confluence == "boost" else ""
                                reason = f"BTC: funding_z={funding_z:.3f} < -1, bear, FGI={fgi}{dxy_tag} → LONG"
                        else:
                            reason = f"BTC: z={funding_z:.3f}, bear, but FGI={fgi}≥40 → no signal (need Fear)"
                else:
                    if -1.0 < funding_z < -0.2:
                        if dxy_confluence == "headwind":
                            reason = f"BTC: z={funding_z:.3f} pullback but DXY strong ({dxy_10d_roc:+.1f}%) → skip"
                        else:
                            signal_type = SignalType.SIGNAL_LONG
                            reason = f"BTC: funding_z={funding_z:.3f} in [-1,-0.2], bull pullback → LONG"
                    elif funding_z <= -1.0:
                        reason = f"BTC: z={funding_z:.3f}≤-1 in bull → no signal (too extreme for bull)"
                    else:
                        reason = f"BTC: z={funding_z:.3f} > -0.2 in bull → no pullback signal"

            # ETH: Bear z<-1, Bull Pullback z∈[-1,-0.2]
            elif symbol == "ETHUSDT":
                if not bull200:
                    if funding_z < self.p["funding_z_long_threshold"]:
                        if dxy_confluence == "headwind":
                            reason = f"ETH: z={funding_z:.3f}, bear but DXY strong ({dxy_10d_roc:+.1f}%) → skip"
                        else:
                            signal_type = SignalType.SIGNAL_LONG
                            reason = f"ETH: funding_z={funding_z:.3f} < -1, bear regime → LONG"
                else:
                    if -1.0 < funding_z < -0.2:
                        if dxy_confluence == "headwind":
                            reason = f"ETH: z={funding_z:.3f} pullback but DXY strong ({dxy_10d_roc:+.1f}%) → skip"
                        else:
                            signal_type = SignalType.SIGNAL_LONG
                            reason = f"ETH: funding_z={funding_z:.3f} in [-1,-0.2], bull pullback → LONG"
                    elif funding_z <= -1.0:
                        reason = f"ETH: z={funding_z:.3f}≤-1 in bull → no signal (too extreme for bull)"
                    else:
                        reason = f"ETH: z={funding_z:.3f} > -0.2 in bull → no pullback signal"

            # SOL: z∈[-0.5, 0) + bull200 (V13b champion)
            elif symbol == "SOLUSDT":
                if -0.5 <= funding_z < 0 and bull200:
                    if dxy_confluence == "headwind":
                        reason = f"SOL: z={funding_z:.3f} ∈ [-0.5,0), bull200 but DXY strong ({dxy_10d_roc:+.1f}%) → skip"
                    else:
                        signal_type = SignalType.SIGNAL_LONG
                        dxy_tag = " 📉weakDXY" if dxy_confluence == "boost" else ""
                        reason = f"SOL: funding_z={funding_z:.3f} ∈ [-0.5, 0), bull200{dxy_tag} → LONG (V13b champion)"
                elif funding_z < -0.5 and bull200:
                    if dxy_confluence == "headwind":
                        reason = f"SOL: z={funding_z:.3f} < -0.5, bull200 but DXY strong ({dxy_10d_roc:+.1f}%) → skip"
                    else:
                        signal_type = SignalType.SIGNAL_LONG
                        reason = f"SOL: funding_z={funding_z:.3f} < -0.5, bull200 → LONG (extended)"
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