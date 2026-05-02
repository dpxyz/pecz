"""
Foundry V11 — Multi-Filter Strategy Evaluation
Tests funding_z<-1 combined with FGI, DXY, OI filters on 2.5 years of historical data.
Goal: Find if any filter combination improves on bare z<-1.
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("research/data_v10")
RESEARCH_DIR = Path("research")

# ── Load historical FGI ──
def load_fgi() -> pd.DataFrame:
    with open(RESEARCH_DIR / "fgi_history.json") as f:
        entries = json.load(f)
    df = pd.DataFrame(entries)
    df['date'] = pd.to_datetime(df['timestamp'].astype(int), unit='s').dt.date
    df['value'] = df['value'].astype(int)
    return df[['date', 'value', 'value_classification']].drop_duplicates('date').set_index('date')

# ── Load historical DXY ──
def load_dxy() -> pd.DataFrame:
    df = pd.read_parquet(RESEARCH_DIR / "dxy_history.parquet")
    df.index = df.index.tz_localize(None)
    df['date'] = df.index.date
    df['dxy_5d_chg'] = df['Close'].pct_change(5) * 100
    # Forward-fill weekends
    daily = df[['Close', 'dxy_5d_chg']].resample('D').ffill()
    daily['date'] = daily.index.date
    return daily.set_index('date')

# ── Merge FGI + DXY into asset data ──
def enrich_asset(df: pd.DataFrame, fgi: pd.DataFrame, dxy: pd.DataFrame) -> pd.DataFrame:
    df['date'] = pd.to_datetime(df['timestamp'], unit='ms').dt.date
    
    # Merge FGI
    df = df.merge(fgi, left_on='date', right_index=True, how='left')
    df.rename(columns={'value': 'fgi', 'value_classification': 'fgi_class'}, inplace=True)
    df['fgi'] = df['fgi'].ffill()
    df['fgi_class'] = df['fgi_class'].ffill()
    
    # Merge DXY
    df = df.merge(dxy[['Close', 'dxy_5d_chg']], left_on='date', right_index=True, how='left', suffixes=('', '_dxy'))
    df.rename(columns={'Close': 'dxy', 'dxy_5d_chg': 'dxy_5d_chg'}, inplace=True)
    df['dxy'] = df['dxy'].ffill()
    df['dxy_5d_chg'] = df['dxy_5d_chg'].ffill()
    
    df.drop(columns=['date'], inplace=True)
    return df

# ── Backtest a single strategy ──
def backtest_strategy(df: pd.DataFrame, entry_fn, exit_hours: int = 24,
                      fee_pct: float = 0.04, slippage_bps: float = 3.0) -> dict:
    """
    Simple backtest: enter on signal, hold exit_hours, close.
    Returns dict with trade stats.
    """
    trades = []
    i = 0
    n = len(df)
    
    while i < n - exit_hours:
        row = df.iloc[i]
        if entry_fn(row):
            entry_price = row['close']
            # Apply slippage
            entry_price_adj = entry_price * (1 + slippage_bps / 10000)
            
            # Hold for exit_hours
            exit_row = df.iloc[min(i + exit_hours, n - 1)]
            exit_price = exit_row['close']
            exit_price_adj = exit_price * (1 - slippage_bps / 10000)
            
            # PnL
            pnl_pct = (exit_price_adj - entry_price_adj) / entry_price_adj * 100 - fee_pct
            
            # Check max DD during hold
            hold_slice = df.iloc[i:i+exit_hours+1]
            max_dd = 0
            peak = entry_price_adj
            for _, hr in hold_slice.iterrows():
                if hr['low'] < peak:
                    dd = (peak - hr['low']) / peak * 100
                    max_dd = max(max_dd, dd)
                if hr['high'] > peak:
                    peak = hr['high']
            
            trades.append({
                'entry_ts': row['timestamp'],
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl_pct': pnl_pct,
                'max_dd': max_dd,
                'fgi': row.get('fgi'),
                'dxy': row.get('dxy'),
                'dxy_5d_chg': row.get('dxy_5d_chg'),
                'funding_z': row.get('funding_z'),
                'bull200': row.get('bull200'),
            })
            i += exit_hours  # Skip ahead (cooldown)
        else:
            i += 1
    
    if not trades:
        return {'n_trades': 0, 'cum_pnl': 0, 'avg_pnl': 0, 'win_rate': 0, 'max_dd': 0}
    
    pnls = [t['pnl_pct'] for t in trades]
    cum = sum(pnls)
    avg = np.mean(pnls)
    wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100
    max_dd = max(t['max_dd'] for t in trades)
    
    # Walk-Forward: split into 6 windows, test OOS
    window_size = len(trades) // 6
    wf_passes = 0
    wf_windows = 0
    for w in range(6):
        start = w * window_size
        end = start + window_size if w < 5 else len(trades)
        window_trades = trades[start:end]
        if not window_trades:
            continue
        w_pnls = [t['pnl_pct'] for t in window_trades]
        w_cum = sum(w_pnls)
        if w_cum > 0:
            wf_passes += 1
        wf_windows += 1
    
    return {
        'n_trades': len(trades),
        'cum_pnl': round(cum, 2),
        'avg_pnl': round(avg, 3),
        'win_rate': round(wr, 1),
        'max_dd': round(max_dd, 1),
        'wf_robustness': f"{wf_passes}/{wf_windows}",
        'wf_pct': round(wf_passes / max(wf_windows, 1) * 100, 0),
        'trades': trades[:5],  # Keep sample
    }

# ── Strategy Definitions ──
STRATEGIES = {
    # Baseline: bare z<-1 (current V2)
    "S01_z_only": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -1.0,
    
    # FGI filters
    "S02_z_fgi_fear": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -1.0 and row.get('fgi', 100) is not None and row['fgi'] < 40,
    "S03_z_fgi_extreme_fear": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -1.0 and row.get('fgi', 100) is not None and row['fgi'] < 25,
    "S04_z_fgi_not_greed": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -1.0 and row.get('fgi', 100) is not None and row['fgi'] <= 50,
    
    # DXY filters
    "S05_z_dxy_weak": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -1.0 and row.get('dxy_5d_chg', 0) is not None and row['dxy_5d_chg'] < 0,
    "S06_z_dxy_very_weak": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -1.0 and row.get('dxy_5d_chg', 0) is not None and row['dxy_5d_chg'] < -0.5,
    "S07_z_dxy_below_100": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -1.0 and row.get('dxy', 200) is not None and row['dxy'] < 100,
    
    # Combined: FGI + DXY
    "S08_z_fgi_dxy": lambda row: (row.get('funding_z', 0) is not None and row['funding_z'] < -1.0 and row.get('fgi', 100) is not None and row['fgi'] < 40 and row.get('dxy_5d_chg', 0) is not None and row['dxy_5d_chg'] < 0),
    "S09_z_fgi_dxy_strict": lambda row: (row.get('funding_z', 0) is not None and row['funding_z'] < -1.0 and row.get('fgi', 100) is not None and row['fgi'] < 25 and row.get('dxy_5d_chg', 0) is not None and row['dxy_5d_chg'] < -0.5),
    
    # Regime + FGI/DXY
    "S10_z_bear_fgi": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -1.0 and row.get('bull200', 0) == 0 and row.get('fgi', 100) is not None and row['fgi'] < 40,
    "S11_z_bull_dxy": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -1.0 and row.get('bull200', 0) == 1 and row.get('dxy_5d_chg', 0) is not None and row['dxy_5d_chg'] < 0,
    
    # Deeper z-thresholds
    "S12_z_1.5_only": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -1.5,
    "S13_z_1.5_fgi": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -1.5 and row.get('fgi', 100) is not None and row['fgi'] < 40,
    "S14_z_2_only": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -2.0,
    
    # BTC bear-only variants
    "S15_z_btc_bear": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -1.0 and row.get('bull200', 0) == 0,
    "S16_z_btc_bear_fgi": lambda row: row.get('funding_z', 0) is not None and row['funding_z'] < -1.0 and row.get('bull200', 0) == 0 and row.get('fgi', 100) is not None and row['fgi'] < 40,
}

def run():
    print("=" * 70)
    print("FOUNDRY V11 — Multi-Filter Strategy Evaluation")
    print("=" * 70)
    
    # Load external data
    fgi = load_fgi()
    dxy = load_dxy()
    print(f"FGI: {len(fgi)} days")
    print(f"DXY: {len(dxy)} days")
    
    assets = ["AVAXUSDT", "BTCUSDT"]
    results = {}
    
    for asset in assets:
        print(f"\n{'='*50}")
        print(f"Asset: {asset}")
        print(f"{'='*50}")
        
        df = pd.read_parquet(DATA_DIR / f"{asset}_1h_full.parquet")
        df = enrich_asset(df, fgi, dxy)
        print(f"Rows: {len(df)}, DXY coverage: {df['dxy'].notna().sum()}/{len(df)}, FGI coverage: {df['fgi'].notna().sum()}/{len(df)}")
        
        asset_results = {}
        for name, entry_fn in STRATEGIES.items():
            result = backtest_strategy(df, entry_fn)
            asset_results[name] = {k: v for k, v in result.items() if k != 'trades'}
            status = "✅" if result['wf_pct'] >= 66 and result['cum_pnl'] > 0 else "❌"
            print(f"  {name:25s} | n={result['n_trades']:3d} | cum={result['cum_pnl']:+7.2f}% | avg={result['avg_pnl']:+.3f}% | WR={result['win_rate']:5.1f}% | DD={result['max_dd']:5.1f}% | WF={result['wf_robustness']:>5s} {status}")
        
        results[asset] = asset_results
    
    # Summary: which strategies improve over baseline?
    print(f"\n{'='*70}")
    print("IMPROVEMENT OVER BASELINE (S01_z_only)")
    print(f"{'='*70}")
    
    for asset in assets:
        baseline = results[asset]['S01_z_only']
        baseline_cum = baseline['cum_pnl']
        baseline_wf = baseline['wf_pct']
        print(f"\n{asset} baseline: cum={baseline_cum:+.2f}%, WF={baseline_wf:.0f}%")
        
        for name, res in results[asset].items():
            if name == 'S01_z_only':
                continue
            delta_cum = res['cum_pnl'] - baseline_cum
            delta_wf = res['wf_pct'] - baseline_wf
            better = "📈" if res['cum_pnl'] > baseline_cum and res['wf_pct'] >= baseline_wf else "📉"
            print(f"  {name:25s} | Δcum={delta_cum:+7.2f}% | ΔWF={delta_wf:+3.0f}% | n={res['n_trades']:3d} {better}")
    
    # Save results
    with open(RESEARCH_DIR / "foundry_v11_results.json", 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to research/foundry_v11_results.json")

if __name__ == "__main__":
    run()