# Pecz — Forward V5 Trading Engine

## Quick Start

```bash
git clone https://github.com/dpxyz/pecz.git
cd pecz
bash install-hooks.sh   # Install pre-commit hook (MUST run after clone!)
```

## Pre-Commit Hook

**This repo has a pre-commit hook that runs the full test suite before allowing commits to executor files.**

If you skip this step, broken tests can be committed silently. Run `bash install-hooks.sh` after cloning.

The hook source is tracked at `forward_5/executor/scripts/pre-commit.sh`.  
It copies itself to `.git/hooks/pre-commit` (not tracked by git).

To reinstall after a `git pull` that changed the hook:
```bash
bash install-hooks.sh
```

## Test Suite

```bash
cd forward_5/executor
python3 -m pytest tests/ -v
```

326 tests (and counting). The pre-commit hook runs these automatically.

## Structure

```
pecz/
├── install-hooks.sh          # Install pre-commit hook
├── forward_5/executor/       # Paper trading engine
│   ├── paper_engine.py       # Main engine
│   ├── state_manager.py      # SQLite state
│   ├── risk_guard.py         # Risk management
│   ├── signal_generator.py   # MACD+ADX+EMA signals
│   ├── data_feed.py          # Hyperliquid REST polling
│   ├── discord_reporter.py   # Discord Components v2
│   ├── monitor.py            # Equity curve + dashboard
│   ├── accounting_check.py   # 8 invariants (daily)
│   ├── watchdog_v2.py        # Health monitoring
│   ├── command_listener.py   # Discord commands
│   └── tests/                # 326 tests
├── docs/site/                # Mission Control (MkDocs)
└── scripts/                  # Housekeeping + monitor cron scripts
```

## Paper Trading Status

Phase 1 (14 days paper) → Phase 2 (14 days testnet API) → V2 Strategy

**See live dashboard:** https://pecz.pages.dev