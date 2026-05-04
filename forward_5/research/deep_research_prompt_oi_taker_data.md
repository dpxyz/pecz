# Deep Research Prompt: Free Historical OI + Taker Ratio Data (6+ Months)

## Context
We're building a crypto trading signal discovery system (Foundry V13). We need **6+ months of historical Open Interest (OI) and Taker Buy/Sell Ratio data** for BTC, ETH, SOL, AVAX, DOGE, ADA on Binance Futures. 

**Current situation:** Binance Futures API (`/futures/data/openInterestHist` and `/futures/data/takerlongshortRatio`) only returns ~30 days of historical data. We need at least 180 days (ideally 365+) for robust statistical validation (CPCV, DSR).

## Requirements
- **Assets:** BTC, ETH, SOL, AVAX, DOGE, ADA (USDT pairs)
- **Timeframe:** 1h or 4h bars
- **History:** Minimum 180 days, ideally 365+ days
- **Cost:** FREE. No paid APIs, no credit card trials.
- **Data points needed:**
  - Open Interest (total OI or OI value, per asset)
  - Taker Buy/Sell Volume Ratio (or buy_vol + sell_vol separately)

## Specific Questions

### 1. Coinalyze Free Tier
- Does Coinalyze offer free historical OI data? How far back?
- What's the rate limit for free users?
- Do they have taker volume data historically?
- Registration required? API key?

### 2. CoinGlass Free Tier  
- Does CoinGlass have a free API tier?
- How much historical OI data is accessible for free?
- Taker ratio historical data available?

### 3. Binance Alternative Endpoints
- `/fapi/v1/openInterest` (current OI) — can we poll historical snapshots?
- `/fapi/v1/ticker/24hr` — does this include taker volume historically?
- Are there Binance Data Vision or Binance Public Data snapshots we can download?
- Binance Data on Google BigQuery or AWS S3?

### 4. Dune Analytics
- Can we query Binance OI from Dune for free?
- Are there existing dashboards/queries for historical OI?
- What's the free tier query limit?

### 5. Alternative.me / Other Free Sources
- Alternative.me OI data — how far back?
- Any other free OI data providers?
- CryptoCompare free tier — OI data?

### 6. Coinglass / CryptoQuant Free Access
- Any way to get historical OI for free from these?
- Web scraping options (terms of service compliant)?

### 7. DIY Approaches
- Can we build OI history by polling Binance spot + futures every hour?
- How long would it take to accumulate 6 months of data at 1h intervals?
- Are there community-maintained OI datasets (GitHub, Kaggle)?

### 8. Proxy Signals
- If OI is not available for free historically, what proxy signals correlate >0.7 with OI?
- Funding rate (which we DO have for 2+ years) as OI proxy?
- Volume as taker ratio proxy?

## Output Format
For each viable data source, provide:
1. **Name** and URL
2. **Data available** (OI, Taker, both?)
3. **Historical depth** (how far back for free)
4. **Rate limits** for free tier
5. **Data format** (REST API, CSV download, SQL query)
6. **Implementation complexity** (easy/medium/hard)
7. **Verdict** (viable or not, and why)

## Priority Order
1. Free REST APIs with 6+ month history
2. Free CSV/bulk downloads
3. Free SQL query platforms (Dune)
4. Proxy signals from data we already have (funding, volume)
5. Web scraping (last resort, must be ToS-compliant)