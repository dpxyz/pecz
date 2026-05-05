#!/usr/bin/env python3
"""
Correlation check between all validated signals.
Computes per-bar PnL series for each signal, then correlates them.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "executor"))

import numpy as np
import polars as pl
from sweep_4h_data import load_all_4h
from sweep_4h_crosssec import compute_cross_sectional_funding
import warnings; warnings.filterwarnings('ignore')

def build_pnl_series(df, entry_mask, hold_bars, direction="long"):
    n = len(df)
    pnl = np.zeros(n)
    close = df["close"].to_numpy()
    occupied = np.zeros(n, dtype=bool)
    i = 0
    while i < n:
        if entry_mask[i] and not occupied[i]:
            entry_price = close[i]
            exit_i = min(i + hold_bars, n - 1)
            exit_price = close[exit_i]
            if direction == "long":
                trade_pnl = (exit_price - entry_price) / entry_price
            else:
                trade_pnl = (entry_price - exit_price) / entry_price
            per_bar = trade_pnl / hold_bars
            for j in range(i, exit_i):
                if not occupied[j]:
                    pnl[j] += per_bar
                    occupied[j] = True
            i = exit_i
        else:
            i += 1
    return pnl

def main():
    data = load_all_4h()
    crosssec = compute_cross_sectional_funding(data)
    
    btc_df = data["BTC"].df
    timestamps = btc_df["timestamp"].to_numpy()
    n = len(timestamps)
    
    signals_config = [
        {"name": "BTC_mild_neg_bull200", "asset": "BTC", "type": "funding", "z_low": -0.5, "z_high": 0.0, "bull": "bull200", "hold_h": 24, "dir": "long"},
        {"name": "ETH_mild_neg_bull200", "asset": "ETH", "type": "funding", "z_low": -0.5, "z_high": 0.0, "bull": "bull200", "hold_h": 24, "dir": "long"},
        {"name": "BTC_slight_neg", "asset": "BTC", "type": "funding", "z_low": -0.5, "z_high": -0.1, "bull": "none", "hold_h": 24, "dir": "long"},
        {"name": "BTC_crosssec_z-1_bull200", "asset": "BTC", "type": "crosssec", "z_low": -2.0, "z_high": -1.0, "bull": "bull200", "hold_h": 24, "dir": "long"},
        {"name": "OI_Surge_SOL_h48", "asset": "SOL", "type": "oi_surge", "threshold": 3.0, "hold_h": 48, "bull": "bull200", "dir": "long"},
        {"name": "OI_Surge_SOL_h24", "asset": "SOL", "type": "oi_surge", "threshold": 3.0, "hold_h": 24, "bull": "bull200", "dir": "long"},
        {"name": "LS_Ratio_SOL_Short", "asset": "SOL", "type": "ls_ratio", "threshold": 5.0, "hold_h": 24, "bull": "none", "dir": "short"},
    ]
    
    pnl_all = {}
    trade_counts = {}
    
    for cfg in signals_config:
        asset = cfg["asset"]
        df = data[asset].df
        
        if cfg["type"] == "funding":
            fz = df["funding_z"].to_numpy()
            bull = df["bull200"].to_numpy().astype(bool) if cfg["bull"] == "bull200" else np.ones(len(df), dtype=bool)
            entry = (fz >= cfg["z_low"]) & (fz < cfg["z_high"]) & bull & ~np.isnan(fz)
        elif cfg["type"] == "crosssec":
            cs_dict = crosssec[asset]
            cs_z = cs_dict.get("z_scores")
            if cs_z is not None:
                cs_arr = cs_z.to_numpy() if hasattr(cs_z, 'to_numpy') else np.array(cs_z)
            else:
                cs_arr = np.zeros(len(df))
            bull = df["bull200"].to_numpy().astype(bool) if cfg["bull"] == "bull200" else np.ones(len(df), dtype=bool)
            entry = (cs_arr >= cfg["z_low"]) & (cs_arr < cfg["z_high"]) & bull
        elif cfg["type"] == "oi_surge":
            oi_pct = df["oi_pct_change"].to_numpy()
            bull = df["bull200"].to_numpy().astype(bool) if cfg["bull"] == "bull200" else np.ones(len(df), dtype=bool)
            entry = (oi_pct > cfg["threshold"]) & bull & ~np.isnan(oi_pct)
        elif cfg["type"] == "ls_ratio":
            ls = df["toptrader_ls_ratio"].to_numpy()
            entry = (ls > cfg["threshold"]) & ~np.isnan(ls)
        
        hold_bars = cfg["hold_h"] // 4
        pnl = build_pnl_series(df, entry, hold_bars, cfg["dir"])
        
        # Align to BTC time index
        if asset != "BTC":
            asset_ts = df["timestamp"].to_numpy()
            aligned = np.zeros(n)
            ts_to_idx = {int(t): i for i, t in enumerate(timestamps)}
            for j, t in enumerate(asset_ts):
                if int(t) in ts_to_idx:
                    aligned[ts_to_idx[int(t)]] = pnl[j]
            pnl_all[cfg["name"]] = aligned
        else:
            pnl_all[cfg["name"]] = pnl
        
        trade_counts[cfg["name"]] = int(entry.sum())
    
    # Correlation matrix
    names = list(pnl_all.keys())
    n_sigs = len(names)
    corr = np.zeros((n_sigs, n_sigs))
    
    for i in range(n_sigs):
        for j in range(n_sigs):
            a = pnl_all[names[i]]
            b = pnl_all[names[j]]
            mask = (a != 0) | (b != 0)
            if mask.sum() < 10:
                corr[i, j] = 0.0
            else:
                a_m, b_m = a[mask], b[mask]
                if np.std(a_m) == 0 or np.std(b_m) == 0:
                    corr[i, j] = 0.0
                else:
                    corr[i, j] = np.corrcoef(a_m, b_m)[0, 1]
    
    print("=== CORRELATION MATRIX (per-bar PnL) ===")
    header = "".join(f"{n[:15]:>16}" for n in names)
    print(f"{'':16}" + header)
    for i, name in enumerate(names):
        row = f"{name[:15]:16}" + "".join(f"{corr[i,j]:>16.2f}" for j in range(n_sigs))
        print(row)
    
    print("\n=== SIGNIFICANT CORRELATIONS ===")
    for i in range(n_sigs):
        for j in range(i+1, n_sigs):
            r = corr[i, j]
            if abs(r) > 0.4:
                emoji = "🔴" if abs(r) > 0.7 else "⚠️"
                print(f"  {emoji} {names[i]} ↔ {names[j]}: rho = {r:.2f}")
            elif abs(r) > 0.2:
                print(f"  🟡 {names[i]} ↔ {names[j]}: rho = {r:.2f}")
    
    print("\n=== SIGNAL SUMMARY ===")
    for name in names:
        pnl = pnl_all[name]
        active = (pnl != 0).sum()
        total = pnl.sum()
        print(f"  {name:35} entries={trade_counts[name]:4d}  active_bars={active:4d}  cum_pnl={total:+.4f}")
    
    print("\n=== PORTFOLIO ORTHOGONALITY CHECK (rho < 0.4) ===")
    uncorrelated = [names[0]]
    for name in names[1:]:
        idx = names.index(name)
        is_uncorr = True
        for u in uncorrelated:
            u_idx = names.index(u)
            if abs(corr[idx, u_idx]) >= 0.4:
                is_uncorr = False
                print(f"  ❌ {name} excluded (rho={corr[idx,u_idx]:.2f} with {u})")
                break
        if is_uncorr:
            uncorrelated.append(name)
            print(f"  ✅ {name} added (rho<0.4 with all existing)")
    
    print(f"\n  UNCORRELATED PORTFOLIO: {len(uncorrelated)} signals")
    for u in uncorrelated:
        print(f"    - {u}")

if __name__ == "__main__":
    main()
