#!/usr/bin/env python3
"""V10 Phase 1e/1f/1g — SL Optimization, HL Cross-Validation, Funding+Regime"""

import polars as pl
import json
import math
from pathlib import Path
from datetime import datetime, timedelta

DATA_DIR = Path("/data/.openclaw/workspace/forward_v5/forward_5/data_collector/data")
OUT_FILE = Path("/data/.openclaw/workspace/forward_v5/forward_5/research/v10_phase1_results.json")

COST_RT = 0.001  # 0.04% maker + 0.06% slippage per round-trip
HOLD_HOURS = 24
HOLD_CANDLES_8H = HOLD_HOURS // 8  # 3 candles

ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]

# ─── Load & prep data ───────────────────────────────────────────────

def load_bn_data():
    funding = pl.read_parquet(DATA_DIR / "bn_funding_1yr.parquet").with_columns(
        pl.col("timestamp").cast(pl.Datetime("ms")).alias("ts")
    ).drop("timestamp").rename({"ts": "timestamp"}).sort(["asset", "timestamp"])

    prices = pl.read_parquet(DATA_DIR / "prices_8h.parquet").with_columns(
        pl.col("timestamp").cast(pl.Datetime("ms")).alias("ts")
    ).drop("timestamp").rename({"ts": "timestamp"}).sort(["asset", "timestamp"])

    return funding, prices


def load_hl_data():
    funding = pl.read_parquet(DATA_DIR / "hl_funding.parquet").sort(["asset", "timestamp"])
    prices = pl.read_parquet(DATA_DIR / "prices_1h.parquet").sort(["asset", "timestamp"])
    return funding, prices


# ─── Walk-forward windows ────────────────────────────────────────────

def make_wf_windows(prices, n_windows=10, train_weeks=5, test_weeks=5):
    """Create non-overlapping walk-forward windows from price data."""
    all_ts = prices.select("timestamp").unique().sort("timestamp")
    t0 = all_ts[0, 0]
    t1 = all_ts[-1, 0]
    window_td = timedelta(days=(train_weeks + test_weeks) * 7)
    train_td = timedelta(weeks=train_weeks)

    windows = []
    for i in range(n_windows):
        ws = t0 + timedelta(days=i * (train_weeks + test_weeks) * 7)
        train_start = ws
        train_end = ws + train_td
        test_start = train_end
        test_end = ws + window_td
        windows.append((train_start, train_end, test_start, test_end))

    return windows


# ─── Test 1: SL Optimization ────────────────────────────────────────

def test_sl_optimization():
    print("\n=== TEST 1: SL OPTIMIZATION ===")
    funding, prices = load_bn_data()
    windows = make_wf_windows(prices)
    sl_levels = [0.03, 0.04, 0.05, 0.06, 0.08, 0.10, None]  # None = no SL

    results = {}
    best_sl_per_asset = {}

    for sl in sl_levels:
        sl_label = f"{int(sl*100)}%" if sl else "no_sl"
        print(f"\n  Testing SL={sl_label}...")

        asset_results = {}
        for asset in ASSETS:
            p = prices.filter(pl.col("asset") == asset).sort("timestamp")
            f = funding.filter(pl.col("asset") == asset).sort("timestamp")

            # Merge funding into prices
            merged = p.join_asof(f.select(["timestamp", "funding_rate"]), on="timestamp", strategy="nearest")

            long_returns = []
            short_returns = []

            for train_s, train_e, test_s, test_e in windows:
                test_data = merged.filter(
                    (pl.col("timestamp") >= test_s) & (pl.col("timestamp") < test_e)
                )
                if test_data.height < HOLD_CANDLES_8H + 1:
                    continue

                closes = test_data["close"].to_list()
                lows = test_data["low"].to_list()
                highs = test_data["high"].to_list()
                fundings = test_data["funding_rate"].to_list()

                for i in range(0, len(closes) - HOLD_CANDLES_8H, HOLD_CANDLES_8H):
                    entry_close = closes[i]
                    if entry_close <= 0:
                        continue

                    # Long: entry at close, hold 24h
                    long_exit = closes[i + HOLD_CANDLES_8H]
                    long_ret = (long_exit / entry_close) - 1.0

                    # Short: entry at close, hold 24h
                    short_ret = (entry_close / long_exit) - 1.0

                    # Funding: negative rate = received by longs
                    fund_sum = sum(fundings[i:i+HOLD_CANDLES_8H])
                    long_fund = fund_sum  # longs receive negative funding
                    short_fund = -fund_sum  # shorts pay funding

                    # SL check for long
                    long_sl_hit = False
                    if sl is not None:
                        for j in range(i+1, i + HOLD_CANDLES_8H + 1):
                            if j < len(lows):
                                if lows[j] <= entry_close * (1 - sl):
                                    long_sl_hit = True
                                    long_ret = -sl
                                    break

                    # SL check for short
                    short_sl_hit = False
                    if sl is not None:
                        for j in range(i+1, i + HOLD_CANDLES_8H + 1):
                            if j < len(highs):
                                if highs[j] >= entry_close * (1 + sl):
                                    short_sl_hit = True
                                    short_ret = -sl
                                    break

                    # Apply costs
                    long_net = long_ret - COST_RT + long_fund
                    short_net = short_ret - COST_RT + short_fund

                    long_returns.append({"ret": long_net, "sl_hit": long_sl_hit})
                    short_returns.append({"ret": short_net, "sl_hit": short_sl_hit})

            if long_returns:
                lr = [r["ret"] for r in long_returns]
                sr = [r["ret"] for r in short_returns]
                asset_results[asset] = {
                    "long_win_rate": sum(1 for r in lr if r > 0) / len(lr) * 100,
                    "long_avg_net": sum(lr) / len(lr) * 100,
                    "long_sl_hit_rate": sum(1 for r in long_returns if r["sl_hit"]) / len(long_returns) * 100,
                    "short_win_rate": sum(1 for r in sr if r > 0) / len(sr) * 100,
                    "short_avg_net": sum(sr) / len(sr) * 100,
                    "short_sl_hit_rate": sum(1 for r in short_returns if r["sl_hit"]) / len(short_returns) * 100,
                    "n_trades": len(lr),
                }

        # Aggregate across assets
        long_wins = [asset_results[a]["long_win_rate"] for a in asset_results]
        long_nets = [asset_results[a]["long_avg_net"] for a in asset_results]
        short_wins = [asset_results[a]["short_win_rate"] for a in asset_results]
        short_nets = [asset_results[a]["short_avg_net"] for a in asset_results]

        results[sl_label] = {
            "long_win_rate": sum(long_wins) / len(long_wins) if long_wins else 0,
            "long_avg_net": sum(long_nets) / len(long_nets) if long_nets else 0,
            "short_win_rate": sum(short_wins) / len(short_wins) if short_wins else 0,
            "short_avg_net": sum(short_nets) / len(short_nets) if short_nets else 0,
            "per_asset": asset_results,
        }
        print(f"    SL={sl_label}: Long win={sum(long_wins)/len(long_wins):.1f}% net={sum(long_nets)/len(long_nets):+.3f}% | Short win={sum(short_wins)/len(short_wins):.1f}% net={sum(short_nets)/len(short_nets):+.3f}%")

    # Find best SL per asset (by long avg net for alts, overall for majors)
    for asset in ASSETS:
        best_sl = None
        best_net = -999
        for sl_label, res in results.items():
            if asset in res["per_asset"]:
                # Use average of long and short net for best overall
                avg = (res["per_asset"][asset]["long_avg_net"] + res["per_asset"][asset]["short_avg_net"]) / 2
                if avg > best_net:
                    best_net = avg
                    best_sl = sl_label
        best_sl_per_asset[asset] = best_sl

    return results, best_sl_per_asset


# ─── Test 2: HL Cross-Validation ────────────────────────────────────

def test_hl_crossval():
    print("\n=== TEST 2: HL CROSS-VALIDATION ===")
    bn_funding, bn_prices = load_bn_data()
    hl_funding, hl_prices = load_hl_data()

    # Resample HL funding to 8h (take mean over 8h windows)
    hl_funding_8h = hl_funding.sort(["asset", "timestamp"]).with_columns(
        pl.col("timestamp").dt.truncate("8h").alias("ts_8h")
    ).group_by(["asset", "ts_8h"]).agg(
        pl.col("funding_rate").mean().alias("funding_rate")
    ).rename({"ts_8h": "timestamp"}).sort(["asset", "timestamp"])

    # Resample 1h prices to 8h
    hl_prices_8h = hl_prices.sort(["asset", "timestamp"]).with_columns(
        pl.col("timestamp").dt.truncate("8h").alias("ts_8h")
    ).group_by(["asset", "ts_8h"]).agg([
        pl.col("open").first().alias("open"),
        pl.col("high").max().alias("high"),
        pl.col("low").min().alias("low"),
        pl.col("close").last().alias("close"),
        pl.col("volume").sum().alias("volume"),
    ]).rename({"ts_8h": "timestamp"}).sort(["asset", "timestamp"])

    # Find overlap period
    # Strip timezone for comparison
    bn_min = bn_funding['timestamp'].min()
    bn_max = bn_funding['timestamp'].max()
    hl_min_raw = hl_funding_8h['timestamp'].min()
    hl_max_raw = hl_funding_8h['timestamp'].max()
    # Convert to naive for comparison
    bn_min_dt = bn_min.replace(tzinfo=None) if bn_min.tzinfo else bn_min
    bn_max_dt = bn_max.replace(tzinfo=None) if bn_max.tzinfo else bn_max
    hl_min_dt = hl_min_raw.replace(tzinfo=None) if hl_min_raw.tzinfo else hl_min_raw
    hl_max_dt = hl_max_raw.replace(tzinfo=None) if hl_max_raw.tzinfo else hl_max_raw

    overlap_start = max(bn_min_dt, hl_min_dt)
    overlap_end = min(bn_max_dt, hl_max_dt)
    print(f"  Overlap period: {overlap_start} to {overlap_end}")

    def run_simple_test(prices_df, funding_df, label):
        prices_df = prices_df.sort(["asset", "timestamp"])
        funding_df = funding_df.sort(["asset", "timestamp"])
        merged = prices_df.join_asof(
            funding_df.select(["asset", "timestamp", "funding_rate"]),
            on="timestamp", strategy="nearest", by="asset"
        )

        all_long = []
        all_short = []

        for asset in ASSETS:
            ad = merged.filter(pl.col("asset") == asset).sort("timestamp")
            if ad.height < HOLD_CANDLES_8H + 1:
                continue

            closes = ad["close"].to_list()
            fundings = ad["funding_rate"].to_list()

            for i in range(0, len(closes) - HOLD_CANDLES_8H, HOLD_CANDLES_8H):
                entry = closes[i]
                exit_ = closes[i + HOLD_CANDLES_8H]
                if entry <= 0:
                    continue

                long_ret = (exit_ / entry) - 1.0 - COST_RT
                short_ret = (entry / exit_) - 1.0 - COST_RT
                fund_sum = sum(fundings[i:i+HOLD_CANDLES_8H])

                long_net = long_ret + fund_sum
                short_net = short_ret - fund_sum

                all_long.append(long_net)
                all_short.append(short_net)

        return {
            "long_avg": sum(all_long) / len(all_long) * 100 if all_long else 0,
            "short_avg": sum(all_short) / len(all_short) * 100 if all_short else 0,
            "long_win": sum(1 for r in all_long if r > 0) / len(all_long) * 100 if all_long else 0,
            "short_win": sum(1 for r in all_short if r > 0) / len(all_short) * 100 if all_short else 0,
            "n_long": len(all_long),
            "n_short": len(all_short),
        }

    # Run on Binance 8h for overlap period - strip tz from overlap bounds
    overlap_start_naive = overlap_start.replace(tzinfo=None) if hasattr(overlap_start, 'tzinfo') else overlap_start
    overlap_end_naive = overlap_end.replace(tzinfo=None) if hasattr(overlap_end, 'tzinfo') else overlap_end

    bn_overlap_f = bn_funding.filter(
        (pl.col("timestamp") >= overlap_start_naive) & (pl.col("timestamp") <= overlap_end_naive)
    )
    bn_overlap_p = bn_prices.filter(
        (pl.col("timestamp") >= overlap_start_naive) & (pl.col("timestamp") <= overlap_end_naive)
    )

    # For HL, strip timezone for comparison
    hl_funding_8h_ntz = hl_funding_8h.with_columns(pl.col('timestamp').dt.replace_time_zone(None).alias('timestamp'))
    hl_prices_8h_ntz = hl_prices_8h.with_columns(pl.col('timestamp').dt.replace_time_zone(None).alias('timestamp'))

    hl_overlap_f = hl_funding_8h_ntz.filter(
        (pl.col("timestamp") >= overlap_start_naive) & (pl.col("timestamp") <= overlap_end_naive)
    )
    hl_overlap_p = hl_prices_8h_ntz.filter(
        (pl.col("timestamp") >= overlap_start_naive) & (pl.col("timestamp") <= overlap_end_naive)
    )

    bn_res = run_simple_test(bn_overlap_p, bn_overlap_f, "Binance 8h (overlap)")
    hl_res = run_simple_test(hl_overlap_p, hl_overlap_f, "HL 8h (overlap)")

    print(f"  Binance 8h (overlap): Long={bn_res['long_avg']:+.3f}% Short={bn_res['short_avg']:+.3f}%")
    print(f"  HL 8h:                 Long={hl_res['long_avg']:+.3f}% Short={hl_res['short_avg']:+.3f}%")

    return {"binance_overlap": bn_res, "hl_8h": hl_res, "overlap_start": str(overlap_start), "overlap_end": str(overlap_end)}


# ─── Test 3: Regime Filter ──────────────────────────────────────────

def test_regime_filter():
    print("\n=== TEST 3: REGIME FILTER ===")
    funding, prices = load_bn_data()

    # Calculate EMAs per asset
    all_regime_data = {}
    for asset in ASSETS:
        p = prices.filter(pl.col("asset") == asset).sort("timestamp")
        closes = p["close"].to_list()
        timestamps = p["timestamp"].to_list()

        # EMA50 (50 candles * 8h = 400h ≈ 16.7 days) and EMA200
        ema50 = [closes[0]]
        k50 = 2 / (50 + 1)
        for c in closes[1:]:
            ema50.append(c * k50 + ema50[-1] * (1 - k50))

        ema200 = [closes[0]]
        k200 = 2 / (200 + 1)
        for c in closes[1:]:
            ema200.append(c * k200 + ema200[-1] * (1 - k200))

        # Regime classification per candle
        regimes = []
        for i in range(len(closes)):
            if i < 200:
                # Not enough data for EMA200, use EMA50 vs close
                if i < 50:
                    regimes.append("neutral")
                elif closes[i] > ema50[i]:
                    regimes.append("bull")
                else:
                    regimes.append("bear")
            else:
                if ema50[i] > ema200[i] * 1.02:
                    regimes.append("bull")
                elif ema50[i] < ema200[i] * 0.98:
                    regimes.append("bear")
                else:
                    regimes.append("neutral")

        all_regime_data[asset] = {
            "timestamps": timestamps,
            "regimes": regimes,
        }

    # Merge regime into price+funding
    merged_all = prices.sort(["asset", "timestamp"]).join_asof(
        funding.select(["asset", "timestamp", "funding_rate"]).sort(["asset", "timestamp"]),
        on="timestamp", strategy="nearest", by="asset"
    )

    # Run tests per regime filter
    def run_regime_test(regime_filter):
        """regime_filter: None=all, 'bull', 'bear', 'non_bear'"""
        longs = []
        shorts = []
        per_asset = {}

        for asset in ASSETS:
            rd = all_regime_data[asset]
            ad = merged_all.filter(pl.col("asset") == asset).sort("timestamp")

            if ad.height < HOLD_CANDLES_8H + 1:
                continue

            closes = ad["close"].to_list()
            fundings = ad["funding_rate"].to_list()

            asset_long = []
            asset_short = []

            for i in range(0, len(closes) - HOLD_CANDLES_8H, HOLD_CANDLES_8H):
                regime = rd["regimes"][i]

                # Filter by regime
                if regime_filter == "bull" and regime != "bull":
                    continue
                elif regime_filter == "bear" and regime != "bear":
                    continue
                elif regime_filter == "non_bear" and regime == "bear":
                    continue

                entry = closes[i]
                exit_ = closes[i + HOLD_CANDLES_8H]
                if entry <= 0:
                    continue

                fund_sum = sum(fundings[i:i+HOLD_CANDLES_8H])

                long_ret = (exit_ / entry) - 1.0 - COST_RT + fund_sum
                short_ret = (entry / exit_) - 1.0 - COST_RT - fund_sum

                asset_long.append(long_ret)
                asset_short.append(short_ret)

            if asset_long:
                per_asset[asset] = {
                    "long_avg": sum(asset_long) / len(asset_long) * 100,
                    "short_avg": sum(asset_short) / len(asset_short) * 100,
                    "long_win": sum(1 for r in asset_long if r > 0) / len(asset_long) * 100,
                    "short_win": sum(1 for r in asset_short if r > 0) / len(asset_short) * 100,
                    "n": len(asset_long),
                }
                longs.extend(asset_long)
                shorts.extend(asset_short)

        return {
            "long_avg": sum(longs) / len(longs) * 100 if longs else 0,
            "short_avg": sum(shorts) / len(shorts) * 100 if shorts else 0,
            "long_win": sum(1 for r in longs if r > 0) / len(longs) * 100 if longs else 0,
            "short_win": sum(1 for r in shorts if r > 0) / len(shorts) * 100 if shorts else 0,
            "n_trades": len(longs),
            "per_asset": per_asset,
        }

    results = {}
    for label, filt in [("always", None), ("bull_only", "bull"), ("bear_only", "bear"), ("non_bear", "non_bear")]:
        res = run_regime_test(filt)
        results[label] = res
        print(f"  {label}: Long={res['long_avg']:+.3f}% Short={res['short_avg']:+.3f}% n={res['n_trades']}")

    return results


# ─── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting V10 Phase 1e/1f/1g tests...")
    print("=" * 60)

    sl_results, best_sl = test_sl_optimization()
    hl_results = test_hl_crossval()
    regime_results = test_regime_filter()

    # Save all results
    all_results = {
        "sl_optimization": {"results": sl_results, "best_sl_per_asset": best_sl},
        "hl_crossval": hl_results,
        "regime_filter": regime_results,
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {OUT_FILE}")

    # ─── Print Summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("=== SL OPTIMIZATION ===")
    print(f"{'SL%':<8} {'Long Win%':<12} {'Long Net%':<12} {'Short Win%':<12} {'Short Net%':<12}")
    for sl_label, res in sl_results.items():
        print(f"{sl_label:<8} {res['long_win_rate']:<12.1f} {res['long_avg_net']:<12.3f} {res['short_win_rate']:<12.1f} {res['short_avg_net']:<12.3f}")

    print(f"\nBest SL per asset: {best_sl}")

    print("\n=== HL CROSS-VALIDATION ===")
    print(f"{'Source':<15} {'Long Edge':<12} {'Short Edge':<12} {'Period'}")
    bn = hl_results["binance_overlap"]
    hl = hl_results["hl_8h"]
    print(f"{'Binance 8h':<15} {bn['long_avg']:<12.3f} {bn['short_avg']:<12.3f} overlap")
    print(f"{'HL 8h':<15} {hl['long_avg']:<12.3f} {hl['short_avg']:<12.3f} full HL")

    print("\n=== REGIME FILTER ===")
    print(f"{'Filter':<12} {'Long Net%':<12} {'Short Net%':<12} {'N Trades'}")
    for label, res in regime_results.items():
        print(f"{label:<12} {res['long_avg']:<12.3f} {res['short_avg']:<12.3f} {res['n_trades']}")

    # Kill criteria check
    always_long = regime_results["always"]["long_avg"]
    always_short = regime_results["always"]["short_avg"]
    annual_long = always_long * (365 / 1)  # per-trade avg * trades/year approximation
    annual_short = always_short * (365 / 1)

    print("\n=== KILL CRITERIA CHECK ===")
    print(f"- Net edge > 0.3% annualized: {'PASS' if max(abs(annual_long), abs(annual_short)) > 0.3 else 'FAIL'} (long={annual_long:+.2f}%, short={annual_short:+.2f}%)")
    print(f"- Edge consistent across exchanges: {'PASS' if (hl['long_avg'] * bn['long_avg'] > 0 or hl['short_avg'] * bn['short_avg'] > 0) else 'FAIL'}")
    bull_long = regime_results["bull_only"]["long_avg"]
    bear_short = regime_results["bear_only"]["short_avg"]
    print(f"- Regime filter improves: {'YES' if bull_long > always_long or bear_short > always_short else 'NO'}")
    print(f"- Best SL for live: {max(best_sl.items(), key=lambda x: x[1])[0] if best_sl else 'N/A'}")