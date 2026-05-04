"""V2 Data Collector Configuration."""

from pathlib import Path

ASSETS = ["BTC", "ETH", "SOL", "AVAX", "DOGE", "ADA"]
BINANCE_SYMBOLS = [f"{a}USDT" for a in ASSETS]

DATA_DIR = Path(__file__).parent / "data"
POLL_INTERVAL = 3600  # seconds

BACKFILL_DAYS = {
    "hyperliquid": 90,
    "binance_funding": 90,
    "binance_oi": 180,
    "binance_ls_ratio": 30,
    "binance_taker": 180,
    "fear_greed": None,  # all available
}

RATE_LIMIT_PER_SECOND = 10
MAX_RETRIES = 5
RETRY_BASE_DELAY = 1.0  # seconds