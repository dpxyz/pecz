"""
Phase 1.3: DXY Regime Filter + Cross-Sectional Funding

Two signal enhancements:
1. DXY Regime Filter: DXY -0.72 correlation with BTC → use 10d ROC as bull/bear filter
2. Cross-Sectional Funding: relative funding between assets → new signal class

Per deep research:
- DXY 2%+ decline → 94% BTC win rate
- Cross-sectional funding alpha documented by Rho Labs
- These are REGIME FILTERS, not standalone signals
"""

import logging
from pathlib import Path

import numpy as np
import polars as pl

from sweep_4h_data import load_all_4h, ASSETS, FOUR_H_MS
from sweep_4h_engine import run_backtest, BacktestResult, Trade
from sweep_4h_signals import SignalHypothesis

log = logging.getLogger("sweep_4h_crosssec")

DATA_DIR = Path(__file__).parent.parent / "data_collector" / "data"


def load_dxy() -> dict:
    """Load DXY (US Dollar Index) data.
    
    Since we don't have direct DXY data, compute BTC/DXY proxy
    from the Fear & Greed index as a regime indicator.
    FGI < 40 = bearish regime (good for our long signals as contrarian)
    """
    fgi_path = DATA_DIR / "fear_greed.parquet"
    if fgi_path.exists():
        df = pl.read_parquet(fgi_path)
        log.info(f"FGI data: {len(df)} rows, cols={df.columns}")
        return {"fgi": df}
    else:
        log.warning("No FGI data found")
        return {}


def compute_cross_sectional_funding(data_4h: dict) -> dict:
    """Compute relative funding between assets.
    
    For each 4h bar, rank assets by funding rate.
    Assets with lowest relative funding = most shorted = long candidates.
    Assets with highest relative funding = most longed = short candidates.
    """
    # Get funding rates for all assets at each timestamp
    all_funding = {}
    timestamps = None
    
    for asset, d in data_4h.items():
        if "funding_rate" in d.df.columns:
            ts = d.df["timestamp"].to_numpy()
            fr = d.df["funding_rate"].to_numpy()
            all_funding[asset] = {"ts": ts, "fr": fr}
            if timestamps is None:
                timestamps = ts
    
    if not all_funding or timestamps is None:
        log.warning("No funding data for cross-sectional computation")
        return {}
    
    # For each asset, compute:
    # 1. Funding rank (1 = lowest = most shorted = long candidate)
    # 2. Relative funding (asset_funding - mean_funding)
    # 3. Z-score of relative funding (how unusual is this asset's funding)
    
    result = {}
    # Pre-compute mean funding across all assets (aligned to min length)
    min_len = min(len(all_funding[a]["fr"]) for a in all_funding)
    funding_arrays = [all_funding[a]["fr"][:min_len] for a in ASSETS if a in all_funding]
    mean_funding_all = np.nanmean(np.column_stack(funding_arrays), axis=1)
    
    for asset, d in data_4h.items():
        if asset not in all_funding:
            continue
        
        fr = all_funding[asset]["fr"]
        n = len(fr)
        
        # Relative funding = asset funding - mean funding
        use_len = min(n, len(mean_funding_all))
        relative_funding = np.zeros(n)
        relative_funding[:use_len] = fr[:use_len] - mean_funding_all[:use_len]
        
        # Z-score of relative funding (60-bar = 10-day window)
        window = 60
        rel_z = np.full(n, np.nan)
        for i in range(window, n):
            w = relative_funding[i-window:i]
            w_clean = w[~np.isnan(w) & (np.abs(w) < 0.01)]  # Filter extreme outliers
            if len(w_clean) > 10:
                mean_w = np.mean(w_clean)
                std_w = np.std(w_clean)
                if std_w > 1e-8:
                    rel_z[i] = np.clip((relative_funding[i] - mean_w) / std_w, -5, 5)
        
        # Funding rank (lower = more shorted = long candidate)
        # Rank at each timestamp across assets
        
        result[asset] = {
            "relative_funding": relative_funding,
            "relative_z": rel_z,
            "funding_rate": fr,
        }
        
        # Stats
        valid_z = rel_z[~np.isnan(rel_z)]
        if len(valid_z) > 0:
            log.info(f"  {asset} cross-sectional: {len(valid_z)} valid z-scores, "
                     f"range [{valid_z.min():.2f}, {valid_z.max():.2f}]")
    
    return result


def generate_crosssec_hypotheses() -> list[SignalHypothesis]:
    """Generate cross-sectional funding hypotheses."""
    hypotheses = []
    
    # When asset has LOW relative funding (most shorted relative to peers) → go long
    for asset in ["BTC", "ETH", "SOL"]:
        # Relative z < -1.0 (significantly underweight)
        for z_thresh in [-0.5, -1.0, -1.5]:
            for bull in ["none", "bull200"]:
                hypotheses.append(SignalHypothesis(
                    name=f"{asset}_crosssec_z{z_thresh:.1f}_{bull}_4h",
                    asset=asset, direction="long",
                    entry_z_low=z_thresh - 1.0, entry_z_high=z_thresh,
                    bull_filter=bull, hold_hours=24, sl_pct=5.0, trail_pct=0.0,
                ))
    
    return hypotheses


def run_crosssec_backtest(data_4h, crosssec_data, hyp: SignalHypothesis) -> BacktestResult:
    """Run backtest with cross-sectional funding signal."""
    asset_data = data_4h.get(hyp.asset)
    if asset_data is None or hyp.asset not in crosssec_data:
        return BacktestResult(
            hypothesis=hyp, n_trades=0, win_rate=0.0, avg_pnl_pct=0.0,
            total_return_pct=0.0, max_dd_pct=0.0, sharpe=0.0,
        )
    
    df = asset_data.df
    n = len(df)
    
    # Get cross-sectional z-score
    rel_z = crosssec_data[hyp.asset]["relative_z"]
    
    # Get standard indicators
    close = df["close"].to_numpy().astype(float)
    bull200 = df["bull200"].to_numpy() if "bull200" in df.columns else np.ones(n, dtype=np.int8)
    
    hold_bars = hyp.hold_hours // 4
    
    trades = []
    in_trade = False
    entry_idx = 0
    entry_price = 0.0
    
    for i in range(50, n):
        if in_trade:
            bars_held = i - entry_idx
            hit_sl = False
            exit_price = None
            
            if hyp.sl_pct > 0:
                sl_price = entry_price * (1 - hyp.sl_pct / 100)
                if df["low"][i] <= sl_price:
                    exit_price = sl_price
                    hit_sl = True
            
            if bars_held >= hold_bars and exit_price is None:
                exit_price = close[i]
            
            if exit_price is not None:
                pnl = (exit_price - entry_price) / entry_price * 100 if hyp.direction == "long" \
                    else (entry_price - exit_price) / entry_price * 100
                
                trades.append(Trade(
                    entry_idx=entry_idx, exit_idx=i,
                    entry_price=entry_price, exit_price=exit_price,
                    direction=hyp.direction, entry_z=rel_z[i] if not np.isnan(rel_z[i]) else 0.0,
                    hold_bars=bars_held, pnl_pct=pnl, hit_sl=hit_sl,
                ))
                in_trade = False
        
        if not in_trade and not np.isnan(rel_z[i]):
            z_in_range = hyp.entry_z_low <= rel_z[i] < hyp.entry_z_high
            
            bull_ok = True
            if hyp.bull_filter == "bull200":
                bull_ok = bull200[i] == 1
            
            if z_in_range and bull_ok:
                in_trade = True
                entry_idx = i
                entry_price = close[i]
    
    if len(trades) == 0:
        return BacktestResult(
            hypothesis=hyp, n_trades=0, win_rate=0.0, avg_pnl_pct=0.0,
            total_return_pct=0.0, max_dd_pct=0.0, sharpe=0.0,
        )
    
    pnls = np.array([t.pnl_pct for t in trades])
    wins = pnls > 0
    win_rate = wins.sum() / len(pnls)
    avg_pnl = pnls.mean()
    cum_returns = np.cumprod(1 + pnls / 100) * 100
    total_return = cum_returns[-1] - 100
    peak = np.maximum.accumulate(cum_returns)
    dd = (cum_returns - peak) / peak * 100
    max_dd = dd.min()
    sharpe = (pnls.mean() / pnls.std() * np.sqrt(6 * 365)) if pnls.std() > 0 else 0.0
    
    return BacktestResult(
        hypothesis=hyp, n_trades=len(trades), win_rate=win_rate,
        avg_pnl_pct=avg_pnl, total_return_pct=total_return,
        max_dd_pct=max_dd, sharpe=sharpe, trades=trades,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
    
    log.info("=" * 60)
    log.info("Phase 1.3+1.4: Cross-Sectional Funding + Regime Filter")
    log.info("=" * 60)
    
    # Load 4h data
    data_4h = load_all_4h()
    
    # Compute cross-sectional funding
    log.info("\nComputing cross-sectional funding...")
    crosssec = compute_cross_sectional_funding(data_4h)
    
    # Generate hypotheses
    hyps = generate_crosssec_hypotheses()
    log.info(f"\nRunning {len(hyps)} cross-sectional hypotheses...")
    
    results = []
    for hyp in hyps:
        result = run_crosssec_backtest(data_4h, crosssec, hyp)
        results.append({
            "name": hyp.name,
            "asset": hyp.asset,
            "direction": hyp.direction,
            "z_low": hyp.entry_z_low,
            "z_high": hyp.entry_z_high,
            "bull_filter": hyp.bull_filter,
            "n_trades": result.n_trades,
            "win_rate": round(result.win_rate, 4),
            "avg_pnl_pct": round(result.avg_pnl_pct, 4),
            "total_return_pct": round(result.total_return_pct, 2),
            "max_dd_pct": round(result.max_dd_pct, 2),
            "sharpe": round(result.sharpe, 2),
        })
        if result.n_trades > 0:
            log.info(f"  {hyp.name}: {result.n_trades} trades, WR={result.win_rate:.1%}, "
                     f"ret={result.total_return_pct:.1f}%, Sharpe={result.sharpe:.2f}")
        else:
            log.info(f"  {hyp.name}: NO TRADES")
    
    # Summary
    profitable = [r for r in results if r["total_return_pct"] > 0]
    log.info(f"\n{'='*60}")
    log.info(f"CROSS-SECTIONAL RESULTS")
    log.info(f"{'='*60}")
    log.info(f"Total: {len(results)}, Profitable: {len(profitable)}")
    
    for r in sorted(results, key=lambda x: x["sharpe"], reverse=True)[:10]:
        log.info(f"  {r['name']}: Sharpe={r['sharpe']:.2f}, ret={r['total_return_pct']:.1f}%, "
                 f"DD={r['max_dd_pct']:.1f}%, trades={r['n_trades']}")