# Pecz — Forward V5 Trading Engine

## Quick Start

```bash
git clone https://github.com/dpxyz/pecz.git
cd pecz
bash install-hooks.sh   # ⚠️ REQUIRED: Installs pre-commit hook (blocks broken tests)
```

## ⚠️ Pre-Commit Hook

**Every commit touching executor files MUST pass `pytest tests/` first.**

The hook lives at `forward_5/executor/scripts/pre-commit.sh` and gets copied to `.git/hooks/pre-commit` by `install-hooks.sh`.

**If you skip this after cloning:** broken tests can be committed silently. Run `bash install-hooks.sh`.

The hook was verified on 2026-04-24: deliberately broken test → commit correctly BLOCKED (exit 1).

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