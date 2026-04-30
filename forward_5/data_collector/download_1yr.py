"""Download 1-year Binance funding rate and 8h price data."""
import requests
import time
import polars as pl
from datetime import datetime, timedelta

SYMBOLS = {
    "BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "SOL",
    "AVAXUSDT": "AVAX", "DOGEUSDT": "DOGE", "ADAUSDT": "ADA"
}

END_MS = int(datetime.now().timestamp() * 1000)
START_MS = int((datetime.now() - timedelta(days=365)).timestamp() * 1000)

def fetch_funding(symbol: str):
    all_records = []
    cursor = START_MS
    while cursor < END_MS:
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&startTime={cursor}&limit=1000"
        r = requests.get(url, timeout=30)
        data = r.json()
        if not data:
            break
        for d in data:
            all_records.append({
                "timestamp": d["fundingTime"],
                "asset": SYMBOLS[symbol],
                "funding_rate": float(d["fundingRate"]),
                "mark_price": float(d.get("markPrice", 0)),
            })
        cursor = int(data[-1]["fundingTime"]) + 1
        time.sleep(0.2)
    return all_records

def fetch_klines(symbol: str):
    all_records = []
    cursor = START_MS
    while cursor < END_MS:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=8h&startTime={cursor}&limit=1500"
        r = requests.get(url, timeout=30)
        data = r.json()
        if not data:
            break
        for d in data:
            all_records.append({
                "timestamp": d[0],
                "asset": SYMBOLS[symbol],
                "open": float(d[1]),
                "high": float(d[2]),
                "low": float(d[3]),
                "close": float(d[4]),
                "volume": float(d[5]),
            })
        cursor = int(data[-1][0]) + 1
        time.sleep(0.2)
    return all_records

# Download funding data
print("Downloading funding data...")
funding_all = []
for sym in SYMBOLS:
    print(f"  Funding: {sym}...")
    records = fetch_funding(sym)
    print(f"    Got {len(records)} records")
    funding_all.extend(records)

df_funding = pl.DataFrame(funding_all)
df_funding.write_parquet("/data/.openclaw/workspace/forward_v5/forward_5/data_collector/data/bn_funding_1yr.parquet")
print(f"Funding data saved: {len(df_funding)} rows")

# Download price data
print("\nDownloading price data...")
price_all = []
for sym in SYMBOLS:
    print(f"  Klines: {sym}...")
    records = fetch_klines(sym)
    print(f"    Got {len(records)} records")
    price_all.extend(records)

df_prices = pl.DataFrame(price_all)
df_prices.write_parquet("/data/.openclaw/workspace/forward_v5/forward_5/data_collector/data/prices_8h.parquet")
print(f"Price data saved: {len(df_prices)} rows")