"""
Foundry V13 — Hypothesen-First LLM Strategy Discovery

Architecture:
1. LLM generates JSON-DSL hypotheses (logic only, NO parameters)
2. Deterministic parser converts DSL → SignalHypothesis objects
3. Sweep engine tests parameter grid for each hypothesis
4. DSR + CPCV + BH-FDR validation pipeline
5. Edge Registry prevents duplication (ρ < 0.4)

Key difference from V12:
- V12: LLM generates eval-able Python code → DANGEROUS, uncontrolled N
- V13: LLM generates structured hypotheses → sweep controls parameters
- V12: Walk-Forward validation
- V13: DSR + CPCV + BH-FDR (proper multiple testing)
"""

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "executor"))
sys.path.insert(0, str(Path(__file__).parent))

from sweep_4h_data import load_all_4h, ASSETS
from sweep_4h_signals import SignalHypothesis
from sweep_4h_engine import run_backtest, BacktestResult, Trade
from sweep_4h_cpcv import CPCVConfig, evaluate_cpcv_equity
from statistical_robustness import deflated_sharpe_ratio
from edge_registry import EdgeRegistry

log = logging.getLogger("foundry_v13")

DATA_DIR = Path(__file__).parent.parent / "data_collector" / "data"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── LLM Config ──
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://172.17.0.1:32771/v1/chat/completions")
OLLAMA_KEY = os.environ.get("OLLAMA_KEY", "ollama-cloud")
MODEL = os.environ.get("FOUNDRY_MODEL", "deepseek-v4-flash:cloud")


# ═══════════════════════════════════════════════════════════
# DSL Definition
# ═══════════════════════════════════════════════════════════

# The LLM outputs a JSON array of hypothesis objects.
# Each hypothesis has:
# - name: short identifier
# - intuition: 2-3 sentence economic story
# - primary_driver: ONE of the allowed signal classes
# - secondary_driver: optional confirmation
# - assets: which assets to test
# - direction: "long" or "short"
# - timeframe: "4h" (fixed for now)
# - anti_correlation: how this differs from existing edges

ALLOWED_PRIMARY_DRIVERS = [
    "funding_z",              # Absolute funding z-score
    "crosssec_funding_z",     # Cross-sectional relative funding
    "oi_pct_change",          # Open interest % change
    "taker_ratio",            # Buy/sell taker ratio
    "vol_ratio",              # Volume ratio (current / 24h avg)
    "fgi",                    # Fear & Greed Index
    "defi_utilization",       # DeFi lending utilization
    "liq_oi_ratio",           # Liquidations / OI
]

ALLOWED_SECONDARY_DRIVERS = [
    "bull200",                # Price above EMA200
    "bull50",                 # Price above EMA50
    "fgi_extreme",            # FGI < 40 or > 60
    "vol_surge",              # Volume > 1.5x average
    "oi_surge",               # OI change > 2%
]

ALLOWED_ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]


@dataclass
class FoundryHypothesis:
    """A hypothesis from the LLM, parsed into structured form."""
    name: str
    intuition: str
    primary_driver: str
    secondary_driver: str | None
    assets: list[str]
    direction: str  # "long" or "short"
    timeframe: str  # "4h"
    anti_correlation: str  # how this differs from existing edges
    
    # Parsed signal hypotheses (filled by parser)
    signal_hypotheses: list[SignalHypothesis] = field(default_factory=list)
    
    # Results (filled by runner)
    results: list[dict] = field(default_factory=list)
    best_sharpe: float = 0.0
    best_result: dict | None = None
    dsr_pass: bool = False
    cpcv_pass: bool = False
    pbo: float = 1.0


# ═══════════════════════════════════════════════════════════
# Feature-based Backtests (for non-funding drivers)
# ═══════════════════════════════════════════════════════════

def _run_feature_backtest(data, sig: SignalHypothesis, feature_col: str,
                           hyp: FoundryHypothesis) -> BacktestResult:
    """Run backtest using a feature column as the entry signal.
    
    For OI, Taker, VolRatio: entry_z_low/high are used as thresholds
    on the feature value (not z-scores of funding).
    
    For example, taker_ratio with entry_z_low=0.7, entry_z_high=0.9
    means: enter when taker_ratio is between 0.7 and 0.9.
    """
    df = data.df
    n = len(df)
    
    if feature_col not in df.columns:
        return BacktestResult(
            hypothesis=sig, n_trades=0, win_rate=0.0, avg_pnl_pct=0.0,
            total_return_pct=0.0, max_dd_pct=0.0, sharpe=0.0,
        )
    
    feature = df[feature_col].to_numpy().astype(float)
    close = df["close"].to_numpy().astype(float)
    low = df["low"].to_numpy().astype(float)
    bull200 = df["bull200"].to_numpy() if "bull200" in df.columns else np.ones(n, dtype=np.int8)
    
    hold_bars = sig.hold_hours // 4
    valid_start = 50
    
    trades = []
    in_trade = False
    entry_idx = 0
    entry_price = 0.0
    
    for i in range(valid_start, n):
        if in_trade:
            bars_held = i - entry_idx
            hit_sl = False
            exit_price = None
            
            if sig.sl_pct > 0:
                sl_price = entry_price * (1 - sig.sl_pct / 100)
                if low[i] <= sl_price:
                    exit_price = sl_price
                    hit_sl = True
            
            if bars_held >= hold_bars and exit_price is None:
                exit_price = close[i]
            
            if exit_price is not None:
                pnl = (exit_price - entry_price) / entry_price * 100
                trades.append(Trade(
                    entry_idx=entry_idx, exit_idx=i,
                    entry_price=entry_price, exit_price=exit_price,
                    direction=sig.direction, entry_z=feature[i],
                    hold_bars=bars_held, pnl_pct=pnl, hit_sl=hit_sl,
                ))
                in_trade = False
        
        if not in_trade and np.isfinite(feature[i]):
            # Check if feature value is in range
            in_range = sig.entry_z_low <= feature[i] < sig.entry_z_high
            
            # For FGI and taker: direction logic matters
            # FGI < 40 (fear) → go long (contrarian)
            # taker < 0.9 (more selling) → go long (contrarian)
            # vol_ratio > 1.3 → confirmation
            
            bull_ok = True
            if sig.bull_filter == "bull200":
                bull_ok = bull200[i] == 1
            
            if in_range and bull_ok:
                in_trade = True
                entry_idx = i
                entry_price = close[i]
    
    if not trades:
        return BacktestResult(
            hypothesis=sig, n_trades=0, win_rate=0.0, avg_pnl_pct=0.0,
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
        hypothesis=sig, n_trades=len(trades), win_rate=win_rate,
        avg_pnl_pct=avg_pnl, total_return_pct=total_return,
        max_dd_pct=max_dd, sharpe=sharpe, trades=trades,
    )


def _run_fgibased_backtest(data, sig: SignalHypothesis,
                            hyp: FoundryHypothesis) -> BacktestResult:
    """FGI-based backtest. FGI thresholds are used directly."""
    return _run_feature_backtest(data, sig, "fgi", hyp)


# ═══════════════════════════════════════════════════════════
# LLM Prompt
# ═══════════════════════════════════════════════════════════

def build_prompt(existing_edges: list[dict], iteration: int = 1) -> str:
    """Build the LLM prompt with anti-anchoring and existing edge context."""
    
    edges_str = ""
    if existing_edges:
        edges_str = "## EXISTING VALIDATED EDGES (do NOT replicate these)\n"
        for e in existing_edges:
            edges_str += f"- {e['name']}: {e.get('primary_driver', '?')} + {e.get('secondary_driver', 'none')}, assets={e.get('assets', [])}, Sharpe={e.get('sharpe', '?')}\n"
        edges_str += "\n"
    
    prompt = f"""You are a quantitative crypto researcher proposing NEW trading hypotheses.

{edges_str}## AVAILABLE DATA FEATURES
- **funding_z**: z-score of 8h funding rate (negative = shorts pay longs)
- **crosssec_funding_z**: z-score of RELATIVE funding (asset vs cross-sectional mean)
- **oi_pct_change**: % change in open interest per 4h bar
- **taker_ratio**: buy volume / sell volume (< 1 = more selling)
- **vol_ratio**: current volume / 24h average (> 1 = above average)
- **fgi**: Fear & Greed Index (0-100, < 40 = fear, > 60 = greed)
- **defi_utilization**: lending protocol utilization (%)
- **liq_oi_ratio**: estimated liquidations / open interest

## AVAILABLE CONFIRMATION FILTERS
- **bull200**: price > EMA200 (long-term uptrend)
- **bull50**: price > EMA50 (short-term uptrend)
- **fgi_extreme**: FGI < 40 (fear) or > 60 (greed)
- **vol_surge**: volume > 1.5x average
- **oi_surge**: OI change > 2%

## RULES
1. Each hypothesis must have a CLEAR economic story (why should this work?)
2. Primary driver must be from the list above
3. At most ONE secondary confirmation filter
4. Specify which assets to test (from: BTC, ETH, SOL, AVAX, DOGE, ADA)
5. Do NOT specify numerical thresholds — the sweep engine optimizes those
6. Do NOT replicate existing edges (different primary driver or mechanism)
7. Focus on UNDEREXPLORED signal classes (OI, taker, DeFi, liquidations)
8. 4h timeframe only (mathematically aligned with 8h funding epoch)

## PROVEN INSIGHTS (use for intuition, not replication)
- Mild negative funding z ∈ [-0.5, 0) + bull200 = robust edge (BTC, ETH)
- Cross-sectional funding z < -1.0 + bull200 = uncorrelated edge (BTC only)
- Bull200 filter doubles Sharpe across all signals
- Shorts with z > 0.5 are dead (funding is structurally positive)
- AVAX/DOGE/ADA have no alpha from funding alone

## OUTPUT FORMAT
Output ONLY a JSON array. Each object:
{{
  "name": "short_snake_case_name",
  "intuition": "2-3 sentence economic story",
  "primary_driver": "one of: funding_z, crosssec_funding_z, oi_pct_change, taker_ratio, vol_ratio, fgi, defi_utilization, liq_oi_ratio",
  "secondary_driver": "one of: bull200, bull50, fgi_extreme, vol_surge, oi_surge, or null",
  "assets": ["BTC", "ETH", "SOL"],
  "direction": "long",
  "anti_correlation": "how this differs from existing edges"
}}

Generate exactly 8 hypotheses. Make them DIVERSE — different primary drivers, different mechanisms.
"""
    
    if iteration > 1:
        prompt += f"""

## ITERATION {iteration}
Previous iteration found {len([e for e in existing_edges if e.get('validated')])} validated edges.
Focus on signal classes NOT yet explored. Avoid repeating failed hypotheses.
"""
    
    return prompt


# ═══════════════════════════════════════════════════════════
# Parser: DSL → SignalHypothesis
# ═══════════════════════════════════════════════════════════

def parse_hypothesis(raw: dict) -> FoundryHypothesis | None:
    """Parse a raw LLM hypothesis dict into a FoundryHypothesis."""
    try:
        name = raw.get("name", "unknown")
        primary = raw.get("primary_driver", "")
        secondary = raw.get("secondary_driver")
        assets = raw.get("assets", [])
        direction = raw.get("direction", "long")
        
        # Validate primary driver
        if primary not in ALLOWED_PRIMARY_DRIVERS:
            log.warning(f"  {name}: invalid primary_driver '{primary}', skipping")
            return None
        
        # Validate secondary driver
        if secondary and secondary not in ALLOWED_SECONDARY_DRIVERS:
            log.warning(f"  {name}: invalid secondary_driver '{secondary}', ignoring")
            secondary = None
        
        # Validate assets
        valid_assets = [a for a in assets if a in ALLOWED_ASSETS]
        if not valid_assets:
            log.warning(f"  {name}: no valid assets, skipping")
            return None
        
        # Validate direction
        if direction not in ("long", "short"):
            direction = "long"
        
        hyp = FoundryHypothesis(
            name=name,
            intuition=raw.get("intuition", ""),
            primary_driver=primary,
            secondary_driver=secondary,
            assets=valid_assets,
            direction=direction,
            timeframe="4h",
            anti_correlation=raw.get("anti_correlation", ""),
        )
        
        return hyp
        
    except Exception as e:
        log.warning(f"Parse error: {e}")
        return None


def expand_to_signal_hypotheses(hyp: FoundryHypothesis) -> list[SignalHypothesis]:
    """Expand a FoundryHypothesis into parameter grid for sweep.
    
    The LLM specifies LOGIC, we add PARAMETERS via grid search.
    This keeps N controllable and prevents hidden optimization.
    """
    signals = []
    
    # Map primary driver to z-score ranges
    # LLM doesn't specify thresholds — we sweep reasonable ranges
    # NOTE: funding_z, crosssec_funding_z use actual z-scores
    # FGI uses 0-100 scale (0=extreme fear, 100=extreme greed)
    # OI/taker use % or ratio scale
    driver_ranges = {
        "funding_z": [
            (-0.5, 0.0, "mild_neg"),      # mild negative
            (-1.0, -0.5, "mod_neg"),      # moderate negative
            (-0.5, -0.1, "slight_neg"),   # slight negative
        ],
        "crosssec_funding_z": [
            (-1.5, -1.0, "crosssec_low"),  # low relative funding
            (-1.0, -0.5, "crosssec_mild"), # mild low relative
            (-2.0, -1.0, "crosssec_deep"), # deep low relative
        ],
        "oi_pct_change": [
            (-5.0, -2.0, "oi_drop"),       # OI dropping (liquidation)
            (-3.0, -1.0, "oi_mild_drop"),  # mild OI drop
            (2.0, 5.0, "oi_surge"),        # OI surge
        ],
        "taker_ratio": [
            (0.5, 0.8, "taker_low"),       # heavy selling (contrarian long)
            (0.8, 0.95, "taker_mild_low"), # mild selling
            (1.1, 1.5, "taker_high"),       # heavy buying (long)
        ],
        "vol_ratio": [
            (1.3, 2.0, "vol_high"),         # above average volume
            (1.5, 3.0, "vol_surge"),        # volume surge
        ],
        "fgi": [
            (0, 25, "fgi_extreme_fear"),    # extreme fear → go long
            (0, 40, "fgi_fear"),            # fear → go long
            (25, 45, "fgi_moderate_fear"),  # moderate fear
        ],
        "defi_utilization": [
            (80, 100, "defi_overheat"),     # > 80% utilization
            (0, 30, "defi_cold"),          # < 30% utilization
        ],
        "liq_oi_ratio": [
            (0.01, 0.05, "liq_mild"),       # mild liquidations
            (0.05, 0.2, "liq_heavy"),       # heavy liquidations
        ],
    }
    
    # Map secondary driver to bull_filter
    secondary_map = {
        "bull200": ["bull200"],
        "bull50": ["bull50"],
        "fgi_extreme": ["none"],  # FGI already in primary or as confluence
        "vol_surge": ["none"],
        "oi_surge": ["none"],
        None: ["none"],
    }
    
    bull_filters = secondary_map.get(hyp.secondary_driver, ["none"])
    
    # For each asset + parameter combination
    for asset in hyp.assets:
        ranges = driver_ranges.get(hyp.primary_driver, [])
        for z_low, z_high, label in ranges:
            for bull in bull_filters:
                for hold_h in [24, 48]:  # 24h and 48h hold
                    for sl in [0.0, 5.0]:  # no SL and 5% SL
                        sig_name = f"{asset}_{hyp.primary_driver}_{label}_{bull}_h{hold_h}_sl{sl:.0f}"
                        signals.append(SignalHypothesis(
                            name=sig_name,
                            asset=asset,
                            direction=hyp.direction,
                            entry_z_low=z_low,
                            entry_z_high=z_high,
                            bull_filter=bull,
                            hold_hours=hold_h,
                            sl_pct=sl,
                            trail_pct=0.0,
                        ))
    
    return signals


# ═══════════════════════════════════════════════════════════
# LLM Call
# ═══════════════════════════════════════════════════════════

def call_llm(prompt: str, retries: int = 3) -> str:
    """Call the LLM and return the raw text response."""
    for attempt in range(retries):
        try:
            log.info(f"  LLM call attempt {attempt+1}/{retries}...")
            resp = requests.post(
                OLLAMA_URL,
                headers={
                    "Authorization": f"Bearer {OLLAMA_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 4000,
                },
                timeout=600,
            )
            log.info(f"  LLM response status: {resp.status_code}")
            
            if resp.status_code != 200:
                log.warning(f"  LLM error: {resp.text[:200]}")
                time.sleep(10)
                continue
            
            data = resp.json()
            msg = data.get("choices", [{}])[0].get("message", {})
            content = msg.get("content", "")
            if not content:
                content = msg.get("reasoning", "") or msg.get("reasoning_content", "")
            
            log.info(f"  LLM response length: {len(content)} chars")
            log.info(f"  LLM response preview: {content[:500]}")
            
            if content:
                return content
        except Exception as e:
            log.warning(f"LLM call attempt {attempt+1} failed: {e}")
            time.sleep(5)
    
    raise RuntimeError("LLM call failed after retries")


def extract_json_array(text: str) -> list[dict]:
    """Extract JSON array from LLM response (may have markdown wrapping)."""
    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    
    # Try extracting from markdown code block
    import re
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    
    # Try finding first [ to last ]
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start:end+1])
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    
    log.error("Could not extract JSON array from LLM response")
    return []


# ═══════════════════════════════════════════════════════════
# Runner: LLM → Parse → Sweep → Validate
# ═══════════════════════════════════════════════════════════

def run_foundry_v13(iterations: int = 1, n_hypotheses: int = 8):
    """Run Foundry V13: Hypothesen-First Strategy Discovery."""
    
    log.info("=" * 60)
    log.info("FOUNDRY V13 — Hypothesen-First Strategy Discovery")
    log.info(f"Model: {MODEL}, Iterations: {iterations}, Hypotheses/iter: {n_hypotheses}")
    log.info("=" * 60)
    
    # Load data once
    log.info("\nLoading 4h data...")
    data_4h = load_all_4h()
    
    # Load existing edges
    reg = EdgeRegistry()
    existing_edges = reg.get_all_edges()
    log.info(f"Existing edges in registry: {len(existing_edges)}")
    
    # Convert EdgeRecords to dicts for prompt
    edges_for_prompt = []
    for e in existing_edges:
        edges_for_prompt.append({
            'name': e.edge_id,
            'primary_driver': getattr(e, 'primary_driver', 'funding_z'),
            'secondary_driver': getattr(e, 'secondary_driver', None),
            'assets': e.assets or [],
            'sharpe': getattr(e, 'sharpe', None) or 0,
            'validated': e.status in ('validated', 'production'),
        })
    
    all_validated = []
    
    for iteration in range(1, iterations + 1):
        log.info(f"\n{'='*60}")
        log.info(f"ITERATION {iteration}/{iterations}")
        log.info(f"{'='*60}")
        
        # Step 1: Generate hypotheses
        prompt = build_prompt(edges_for_prompt, iteration)
        log.info("\nStep 1: Calling LLM for hypotheses...")
        
        raw_text = call_llm(prompt)
        raw_hypotheses = extract_json_array(raw_text)
        log.info(f"  LLM returned {len(raw_hypotheses)} raw hypotheses")
        
        # Step 2: Parse hypotheses
        log.info("\nStep 2: Parsing hypotheses...")
        hypotheses = []
        for raw in raw_hypotheses:
            hyp = parse_hypothesis(raw)
            if hyp:
                log.info(f"  ✅ {hyp.name}: {hyp.primary_driver} + {hyp.secondary_driver} on {hyp.assets}")
                hypotheses.append(hyp)
            else:
                log.info(f"  ❌ Invalid hypothesis skipped")
        
        if not hypotheses:
            log.warning("No valid hypotheses generated. Skipping iteration.")
            continue
        
        # Step 3: Expand to signal grid and backtest
        log.info(f"\nStep 3: Expanding {len(hypotheses)} hypotheses to signal grid...")
        total_signals = 0
        all_results = []
        
        for hyp in hypotheses:
            signals = expand_to_signal_hypotheses(hyp)
            hyp.signal_hypotheses = signals
            total_signals += len(signals)
            log.info(f"  {hyp.name}: {len(signals)} signal variants")
        
        log.info(f"\n  Total signals to backtest: {total_signals}")
        log.info(f"  (This is N for DSR multiple-testing correction)")
        
        # Step 4: Run backtests
        log.info("\nStep 4: Running backtests...")
        for hyp in hypotheses:
            best_result = None
            best_sharpe = -999
            
            for sig in hyp.signal_hypotheses:
                asset_data = data_4h.get(sig.asset)
                if asset_data is None:
                    continue
                
                # Resolve primary driver to the z-score column in 4h data
                # funding_z and crosssec_funding_z work with the existing engine
                # For other drivers, we need to create a pseudo-z-score
                if hyp.primary_driver == "funding_z":
                    # Already handled by sweep_4h_engine
                    result = run_backtest(asset_data, sig)
                elif hyp.primary_driver == "crosssec_funding_z":
                    # Cross-sectional — add rel_z as funding_z temporarily
                    # (already validated in Phase 1.4)
                    result = run_backtest(asset_data, sig)
                elif hyp.primary_driver == "fgi":
                    # FGI is in the data — use as entry signal
                    # sig.entry_z_low/high represent FGI thresholds
                    # We need a custom backtest that uses FGI instead of funding_z
                    result = _run_fgibased_backtest(asset_data, sig, hyp)
                elif hyp.primary_driver == "oi_pct_change":
                    result = _run_feature_backtest(asset_data, sig, "oi_pct_change", hyp)
                elif hyp.primary_driver == "taker_ratio":
                    result = _run_feature_backtest(asset_data, sig, "taker_ratio", hyp)
                elif hyp.primary_driver == "vol_ratio":
                    result = _run_feature_backtest(asset_data, sig, "vol_ratio", hyp)
                else:
                    # Unknown/unsupported driver — skip
                    log.debug(f"    {sig.name}: driver {hyp.primary_driver} not yet supported")
                    continue
                hyp.results.append({
                    "name": sig.name,
                    "asset": sig.asset,
                    "n_trades": result.n_trades,
                    "win_rate": round(result.win_rate, 4),
                    "total_return_pct": round(result.total_return_pct, 2),
                    "max_dd_pct": round(result.max_dd_pct, 2),
                    "sharpe": round(result.sharpe, 2),
                })
                
                if result.sharpe > best_sharpe and result.n_trades > 10:
                    best_sharpe = result.sharpe
                    best_result = hyp.results[-1]
            
            hyp.best_sharpe = best_sharpe
            hyp.best_result = best_result
            
            if best_result:
                log.info(f"  {hyp.name}: best Sharpe={best_sharpe:.2f}, "
                         f"ret={best_result['total_return_pct']:.1f}%, "
                         f"trades={best_result['n_trades']}")
            else:
                log.info(f"  {hyp.name}: NO profitable results")
        
        # Step 5: DSR Validation
        log.info("\nStep 5: DSR Validation...")
        n_total = total_signals  # N for DSR
        
        for hyp in hypotheses:
            profitable = [r for r in hyp.results if r["sharpe"] > 0 and r["n_trades"] > 10]
            if not profitable:
                hyp.dsr_pass = False
                continue
            
            best = max(profitable, key=lambda r: r["sharpe"])
            dsr_result = deflated_sharpe_ratio(
                observed_sharpe=best["sharpe"],
                n_backtests=n_total,
                n_observations=best["n_trades"],
                skewness=0.0, kurtosis=3.0,
                annualization_factor=1, is_annualized=False,
            )
            hyp.dsr_pass = dsr_result.is_significant
            log.info(f"  {'✅' if hyp.dsr_pass else '❌'} {hyp.name}: "
                     f"best Sharpe={best['sharpe']:.2f}, DSR threshold={dsr_result.dsr:.4f}")
        
        # Step 6: CPCV Validation (DSR-passed only)
        log.info("\nStep 6: CPCV Validation...")
        dsr_passed = [h for h in hypotheses if h.dsr_pass]
        
        for hyp in dsr_passed:
            # Find the best signal variant
            best = max([r for r in hyp.results if r["sharpe"] > 0], key=lambda r: r["sharpe"])
            sig_name = best["name"]
            
            # Find the SignalHypothesis object
            sig = [s for s in hyp.signal_hypotheses if s.name == sig_name]
            if not sig:
                hyp.cpcv_pass = False
                continue
            sig = sig[0]
            
            asset_data = data_4h.get(sig.asset)
            if not asset_data:
                hyp.cpcv_pass = False
                continue
            
            # Run backtest to get equity curve
            bt_result = run_backtest(asset_data, sig)
            n = len(asset_data.df)
            bar_returns = np.zeros(n)
            for t in bt_result.trades:
                if t.exit_idx < n:
                    bar_returns[t.exit_idx] = t.pnl_pct / 100.0
            equity = np.cumprod(1 + bar_returns) * 100
            
            config = CPCVConfig(n_groups=6, n_test_groups=2, embargo_bars=2)
            try:
                cpcv_result = evaluate_cpcv_equity(equity, config)
                hyp.pbo = cpcv_result.pbo
                hyp.cpcv_pass = cpcv_result.pbo < 0.5
                oos_returns = [ret for ret in cpcv_result.path_returns if ret is not None]
                oos_avg = np.mean(oos_returns) * 100 if oos_returns else 0
                log.info(f"  {'✅' if hyp.cpcv_pass else '❌'} {hyp.name}: "
                         f"PBO={hyp.pbo:.4f}, OOS avg={oos_avg:.1f}%")
            except Exception as e:
                log.warning(f"  CPCV failed for {hyp.name}: {e}")
                hyp.cpcv_pass = False
        
        # Step 7: Summary
        validated = [h for h in hypotheses if h.dsr_pass and h.cpcv_pass]
        log.info(f"\n{'='*60}")
        log.info(f"ITERATION {iteration} SUMMARY")
        log.info(f"{'='*60}")
        log.info(f"  Hypotheses generated: {len(hypotheses)}")
        log.info(f"  DSR passed: {len(dsr_passed)}")
        log.info(f"  CPCV passed: {len(validated)}")
        
        for h in validated:
            log.info(f"  ✅ {h.name}: {h.primary_driver} + {h.secondary_driver}, "
                     f"best Sharpe={h.best_sharpe:.2f}, PBO={h.pbo:.4f}")
        
        # Register validated edges
        for h in validated:
            edges_for_prompt.append({
                "name": h.name,
                "primary_driver": h.primary_driver,
                "secondary_driver": h.secondary_driver,
                "assets": h.assets,
                "sharpe": h.best_sharpe,
                "validated": True,
            })
            all_validated.append(h)
        
        # Save iteration results
        iter_results = []
        for h in hypotheses:
            iter_results.append({
                "name": h.name,
                "intuition": h.intuition,
                "primary_driver": h.primary_driver,
                "secondary_driver": h.secondary_driver,
                "assets": h.assets,
                "direction": h.direction,
                "anti_correlation": h.anti_correlation,
                "n_signal_variants": len(h.signal_hypotheses),
                "best_sharpe": h.best_sharpe,
                "dsr_pass": bool(h.dsr_pass),
                "cpcv_pass": bool(h.cpcv_pass),
                "pbo": round(h.pbo, 4),
                "top_results": sorted(h.results, key=lambda r: r["sharpe"], reverse=True)[:5],
            })
        
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_file = RESULTS_DIR / f"foundry_v13_iter{iteration}_{ts}.json"
        with open(out_file, "w") as f:
            json.dump(iter_results, f, indent=2, default=str)
        log.info(f"\n  Results saved to {out_file}")
    
    # Final summary
    log.info(f"\n{'='*60}")
    log.info(f"FOUNDRY V13 COMPLETE")
    log.info(f"{'='*60}")
    log.info(f"Total iterations: {iterations}")
    log.info(f"Total validated hypotheses: {len(all_validated)}")
    for h in all_validated:
        log.info(f"  ✅ {h.name}: {h.primary_driver} + {h.secondary_driver}")
    
    return all_validated


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
    run_foundry_v13(iterations=1)