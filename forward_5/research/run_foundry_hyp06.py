"""
Foundry HYP-06 — Regime-Adaptive Strategy Evaluation
Manual strategy design based on HYP-01..05 findings.
No LLM generation — deterministic strategies only.
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path

DATA_DIR = Path("research/data_v10")
RESEARCH_DIR = Path("research")

import sys; sys.path.insert(0, str(RESEARCH_DIR))
from run_foundry_v11 import load_fgi, load_dxy, enrich_asset

def walk_forward_gate(df, entry_fn, n_windows=6, exit_hours=24, fee_pct=0.04, slippage_bps=3.0):
    total_len = len(df)
    window_size = total_len // n_windows
    results = []
    for w in range(n_windows):
        oos_start = w * window_size
        oos_end = (w + 1) * window_size if w < n_windows - 1 else total_len
        oos_df = df.iloc[oos_start:oos_end]
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
                    i += exit_hours
                else:
                    i += 1
            except:
                i += 1
        cum_pnl = sum(trades) if trades else 0
        win_rate = sum(1 for t in trades if t > 0) / len(trades) * 100 if trades else 0
        results.append({
            'window': w + 1, 'n_trades': len(trades), 'cum_pnl': round(cum_pnl, 2),
            'win_rate': round(win_rate, 1), 'oos_profitable': cum_pnl > 0,
        })
    n_profitable = sum(1 for r in results if r['oos_profitable'])
    total_oos_pnl = sum(r['cum_pnl'] for r in results)
    total_trades = sum(r['n_trades'] for r in results)
    avg_wr = np.mean([r['win_rate'] for r in results if r['n_trades'] > 0]) if any(r['n_trades'] > 0 for r in results) else 0
    passed = n_profitable >= n_windows * 0.66 and total_oos_pnl > 0 and total_trades >= 30
    return {
        'passed': passed, 'n_profitable': n_profitable, 'n_windows': n_windows,
        'robustness': round(n_profitable / n_windows * 100),
        'total_oos_pnl': round(total_oos_pnl, 2), 'total_trades': total_trades,
        'avg_win_rate': round(avg_wr, 1), 'windows': results,
    }

# ── Regime-Adaptive Strategies ──
# Design principle: Bear = Funding Mean Reversion (validated), Bull = ???
# Bull approaches: EMA trend, funding cross, vol_ratio, DXY, squeeze breakout

STRATEGIES = {
    "RA01_fund_cross_bear_mr": {
        "desc": "Bear=funding z<-1 MR, Bull=funding crosses above 0 (trend start)",
        "entry_bull": "row.get('fund_cross_up',0)==1",
        "entry_bear": "pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0",
    },
    "RA02_squeeze_breakout_bear_mr": {
        "desc": "Bear=funding z<-1 MR, Bull=squeeze breakout (vol expansion)",
        "entry_bull": "row.get('squeeze',0)==1 and row.get('vol_ratio',1)>1.5",
        "entry_bear": "pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0",
    },
    "RA03_ema_trend_fund_cross": {
        "desc": "Bear=funding z<-1 MR, Bull=EMA50>EMA200 + funding crosses up",
        "entry_bull": "row.get('bull50',0)==1 and row.get('fund_cross_up',0)==1",
        "entry_bear": "pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0",
    },
    "RA04_dxy_weak_bull_mr_bear": {
        "desc": "Bear=funding z<-1 MR, Bull=DXY falling (5d<-0.5%) + EMA50>EMA200",
        "entry_bull": "pd.notna(row.get('dxy_5d_chg')) and row['dxy_5d_chg'] < -0.5 and row.get('bull50',0)==1",
        "entry_bear": "pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0",
    },
    "RA05_vol_expansion_trend": {
        "desc": "Bear=funding z<-1 MR, Bull=vol_ratio>1.5 + EMA50>EMA200",
        "entry_bull": "row.get('vol_ratio',1)>1.5 and row.get('bull50',0)==1",
        "entry_bear": "pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0",
    },
    "RA06_fund_negative_bull_pullback": {
        "desc": "Bear=funding z<-1 MR, Bull=mild negative funding in bull (pullback buy)",
        "entry_bull": "row.get('bull200',0)==1 and pd.notna(row.get('funding_z')) and row['funding_z'] < -0.5 and row['funding_z'] > -1.0",
        "entry_bear": "pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0",
    },
    "RA07_fgi_fear_bull_bear_mr": {
        "desc": "Bear=funding z<-1 + FGI<40, Bull=FGI extreme fear in bull (contrarian)",
        "entry_bull": "row.get('bull200',0)==1 and pd.notna(row.get('fgi')) and row['fgi'] < 25",
        "entry_bear": "pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0 and row.get('bull200',1)==0",
    },
    "RA08_fund_cross_down_bull_reentry": {
        "desc": "Bear=funding z<-1 MR, Bull=funding crosses down from positive (dip buy in bull)",
        "entry_bull": "row.get('bull200',0)==1 and row.get('fund_cross_down',0)==1",
        "entry_bear": "pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0",
    },
    "RA09_triple_confirm_bull": {
        "desc": "Bear=funding z<-1 MR, Bull=EMA50>EMA200+vol_ratio>1.2+fund_cross_up",
        "entry_bull": "row.get('bull50',0)==1 and row.get('vol_ratio',1)>1.2 and row.get('fund_cross_up',0)==1",
        "entry_bear": "pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0",
    },
    "RA10_dxy_strong_bear_boost": {
        "desc": "Bear=funding z<-1 + DXY rising (macro bearish boost), Bull=EMA trend",
        "entry_bull": "row.get('bull50',0)==1 and row.get('fund_cross_up',0)==1",
        "entry_bear": "pd.notna(row.get('funding_z')) and row['funding_z'] < -1.0 and pd.notna(row.get('dxy_5d_chg')) and row['dxy_5d_chg'] > 0.5",
    },
}

if __name__ == "__main__":
    fgi = load_fgi()
    dxy = load_dxy()
    
    print("=" * 80)
    print("FOUNDRY HYP-06 — Regime-Adaptive Strategy Evaluation")
    print("10 strategies, Bear=Funding MR, Bull=various approaches")
    print("Gate: ≥4/6 OOS, cum > 0, ≥30 trades")
    print("=" * 80)
    
    all_results = {}
    for asset in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        print(f"\n{'='*60}\n  {asset}\n{'='*60}")
        df = pd.read_parquet(DATA_DIR / f"{asset}_1h_full.parquet")
        df = enrich_asset(df.copy(), fgi, dxy)
        df['funding_z'] = df['funding_z'].replace([np.inf, -np.inf], np.nan)
        df['bull200'] = df['bull200'].fillna(0).astype(int)
        df['bull50'] = df.get('bull50', df['bull200']).fillna(0).astype(int)
        
        for name, spec in STRATEGIES.items():
            entry_bull_expr = spec['entry_bull']
            entry_bear_expr = spec['entry_bear']
            
            def make_entry(bull_expr, bear_expr):
                def entry_fn(row):
                    try:
                        d = dict(row)
                        # Convert NaN to None for safe eval
                        for k, v in d.items():
                            if isinstance(v, float) and (v != v):  # NaN check
                                d[k] = None
                        if d.get('bull200', 0) == 1:
                            return bool(eval(bull_expr, {"__builtins__": {}, "pd": pd, "np": np}, d))
                        else:
                            return bool(eval(bear_expr, {"__builtins__": {}, "pd": pd, "np": np}, d))
                    except:
                        return False
                return entry_fn
            
            entry_fn = make_entry(entry_bull_expr, entry_bear_expr)
            result = walk_forward_gate(df, entry_fn)
            key = f"{asset}_{name}"
            all_results[key] = {**result, 'desc': spec['desc'], 'entry_bull': entry_bull_expr, 'entry_bear': entry_bear_expr}
            status = "✅ PASS" if result['passed'] else "❌ FAIL"
            print(f"\n  {name}: {spec['desc']}")
            print(f"  {status} | OOS={result['n_profitable']}/{result['n_windows']} ({result['robustness']}%) | PnL={result['total_oos_pnl']:+.2f}% | n={result['total_trades']} | WR={result['avg_win_rate']:.1f}%")
            for w in result['windows']:
                mark = "✅" if w['oos_profitable'] else "❌"
                print(f"    W{w['window']}: n={w['n_trades']:3d}, cum={w['cum_pnl']:+7.2f}%, WR={w['win_rate']:5.1f}% {mark}")
    
    print(f"\n{'='*80}\nSUMMARY\n{'='*80}")
    passed_count = 0
    for name, result in all_results.items():
        status = "✅" if result['passed'] else "❌"
        if result['passed']:
            passed_count += 1
        print(f"  {status} {name:55s} | OOS={result['n_profitable']}/{result['n_windows']} | PnL={result['total_oos_pnl']:+7.2f}% | n={result['total_trades']:4d}")
    
    print(f"\n  TOTAL PASSED: {passed_count}/{len(all_results)}")
    
    with open(RESEARCH_DIR / "foundry_hyp06_results.json", 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"  Results saved to research/foundry_hyp06_results.json")