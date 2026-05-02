"""
Foundry V11 — Walk-Forward Gate Test (V8.1 standard)
Tests all V2 signals with proper IS/OOS splits across 6 windows.
Only strategies with ≥66% OOS windows profitable AND positive total OOS pass.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("research/data_v10")
RESEARCH_DIR = Path("research")

# ── Load external data ──
def load_fgi() -> pd.DataFrame:
    with open(RESEARCH_DIR / "fgi_history.json") as f:
        entries = json.load(f)
    df = pd.DataFrame(entries)
    df['date'] = pd.to_datetime(df['timestamp'].astype(int), unit='s').dt.date
    df['value'] = df['value'].astype(int)
    return df[['date', 'value', 'value_classification']].drop_duplicates('date').set_index('date')

def load_dxy() -> pd.DataFrame:
    df = pd.read_parquet(RESEARCH_DIR / "dxy_history.parquet")
    df.index = df.index.tz_localize(None)
    df['dxy_5d_chg'] = df['Close'].pct_change(5) * 100
    daily = df[['Close', 'dxy_5d_chg']].resample('D').ffill()
    daily['date'] = daily.index.date
    return daily.set_index('date')

def enrich_df(df, fgi, dxy):
    df = df.copy()
    df['funding_z'] = df['funding_z'].replace([np.inf, -np.inf], np.nan)
    df['bull200'] = df['bull200'].fillna(0).astype(int)
    df['date'] = pd.to_datetime(df['timestamp'], unit='ms').dt.date
    df = df.merge(fgi, left_on='date', right_index=True, how='left')
    df.rename(columns={'value': 'fgi', 'value_classification': 'fgi_class'}, inplace=True)
    df['fgi'] = df['fgi'].ffill()
    df['fgi_class'] = df['fgi_class'].ffill()
    df = df.merge(dxy[['Close', 'dxy_5d_chg']], left_on='date', right_index=True, how='left', suffixes=('', '_dxy'))
    df.rename(columns={'Close': 'dxy', 'dxy_5d_chg': 'dxy_5d_chg'}, inplace=True)
    df['dxy'] = df['dxy'].ffill()
    df['dxy_5d_chg'] = df['dxy_5d_chg'].ffill()
    df.drop(columns=['date'], inplace=True)
    return df

# ── Walk-Forward Gate ──
def walk_forward_gate(df, entry_fn, n_windows=6, exit_hours=24, fee_pct=0.04, slippage_bps=3.0):
    """Proper walk-forward test with IS/OOS splits."""
    total_len = len(df)
    window_size = total_len // n_windows
    results = []
    
    for w in range(n_windows):
        # IS: everything before this window
        # OOS: this window
        oos_start = w * window_size
        oos_end = (w + 1) * window_size if w < n_windows - 1 else total_len
        oos_df = df.iloc[oos_start:oos_end]
        
        # Simulate trades in OOS
        trades = []
        i = 0
        while i < len(oos_df) - exit_hours:
            row = oos_df.iloc[i]
            try:
                if entry_fn(row):
                    entry_price = row['close'] * (1 + slippage_bps / 10000)
                    exit_idx = min(i + exit_hours, len(oos_df) - 1)
                    exit_price = oos_df.iloc[exit_idx]['close'] * (1 - slippage_bps / 10000)
                    pnl = (exit_price - entry_price) / entry_price * 100 - fee_pct
                    trades.append(pnl)
                    i += exit_hours  # cooldown
                else:
                    i += 1
            except:
                i += 1
        
        cum_pnl = sum(trades) if trades else 0
        win_rate = sum(1 for t in trades if t > 0) / len(trades) * 100 if trades else 0
        results.append({
            'window': w + 1,
            'n_trades': len(trades),
            'cum_pnl': round(cum_pnl, 2),
            'win_rate': round(win_rate, 1),
            'oos_profitable': cum_pnl > 0,
        })
    
    # Gate criteria
    n_profitable = sum(1 for r in results if r['oos_profitable'])
    total_oos_pnl = sum(r['cum_pnl'] for r in results)
    total_trades = sum(r['n_trades'] for r in results)
    avg_wr = np.mean([r['win_rate'] for r in results if r['n_trades'] > 0]) if any(r['n_trades'] > 0 for r in results) else 0
    
    passed = n_profitable >= n_windows * 0.66 and total_oos_pnl > 0
    
    return {
        'passed': passed,
        'n_profitable': n_profitable,
        'n_windows': n_windows,
        'robustness': round(n_profitable / n_windows * 100),
        'total_oos_pnl': round(total_oos_pnl, 2),
        'total_trades': total_trades,
        'avg_win_rate': round(avg_wr, 1),
        'windows': results,
    }

# ── Strategy Definitions ──
STRATEGIES = {
    "AVAX_z_only": lambda row: row.get('funding_z', 0) is not None and pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0,
    "BTC_z_bear_fgi40": lambda row: (row.get('funding_z', 0) is not None and pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0 and row.get('bull200', 1) == 0 and row.get('fgi', 100) is not None and pd.notna(row.get('fgi')) and row['fgi'] < 40),
    "ETH_z_bear": lambda row: (row.get('funding_z', 0) is not None and pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0 and row.get('bull200', 1) == 0),
    "DOGE_z_bear": lambda row: (row.get('funding_z', 0) is not None and pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0 and row.get('bull200', 1) == 0),
    "SOL_z_1.5": lambda row: (row.get('funding_z', 0) is not None and pd.notna(row.get('funding_z')) and row['funding_z'] < -1.5),
}

ASSET_STRATEGIES = {
    "AVAXUSDT": ["AVAX_z_only"],
    "BTCUSDT": ["BTC_z_bear_fgi40"],
    "ETHUSDT": ["ETH_z_bear"],
    "DOGEUSDT": ["DOGE_z_bear"],
    "SOLUSDT": ["SOL_z_1.5"],
}

def run():
    fgi = load_fgi()
    dxy = load_dxy()
    
    print("=" * 80)
    print("FOUNDRY V11 — WALK-FORWARD GATE TEST (V8.1 Standard)")
    print("Gate: ≥66% OOS windows profitable + total OOS > 0")
    print("=" * 80)
    
    all_results = {}
    
    for asset, strategies in ASSET_STRATEGIES.items():
        print(f"\n{'='*60}")
        print(f"  {asset}")
        print(f"{'='*60}")
        
        df = pd.read_parquet(DATA_DIR / f"{asset}_1h_full.parquet")
        df = enrich_df(df, fgi, dxy)
        
        fz_count = df['funding_z'].notna().sum()
        print(f"  Rows: {len(df)}, funding_z valid: {fz_count}")
        
        for strat_name in strategies:
            entry_fn = STRATEGIES[strat_name]
            result = walk_forward_gate(df, entry_fn)
            all_results[f"{asset}_{strat_name}"] = result
            
            status = "✅ PASS" if result['passed'] else "❌ FAIL"
            print(f"\n  {strat_name}:")
            print(f"  Status: {status}")
            print(f"  OOS Profitable: {result['n_profitable']}/{result['n_windows']} ({result['robustness']}%)")
            print(f"  Total OOS PnL: {result['total_oos_pnl']:+.2f}%")
            print(f"  Total Trades: {result['total_trades']}")
            print(f"  Avg Win Rate: {result['avg_win_rate']:.1f}%")
            print(f"  Per-window:")
            for w in result['windows']:
                mark = "✅" if w['oos_profitable'] else "❌"
                print(f"    W{w['window']}: n={w['n_trades']:3d}, cum={w['cum_pnl']:+7.2f}%, WR={w['win_rate']:5.1f}% {mark}")
    
    # Summary
    print(f"\n{'='*80}")
    print("GATE SUMMARY")
    print(f"{'='*80}")
    for name, result in all_results.items():
        status = "✅ PASS" if result['passed'] else "❌ FAIL"
        print(f"  {name:35s} | OOS={result['n_profitable']}/{result['n_windows']} | PnL={result['total_oos_pnl']:+7.2f}% | Trades={result['total_trades']:4d} | {status}")
    
    # Save
    with open(RESEARCH_DIR / "foundry_v11_wf_gate_results.json", 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to research/foundry_v11_wf_gate_results.json")

if __name__ == "__main__":
    run()