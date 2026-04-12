"""
歷史 OHLCV 資料（使用 yfinance）
支援時間框架：3, 6, 15, 60（分鐘）, D（日）, W（週）
"""

import yfinance as yf
import pandas as pd
import shutil, os

# 清除 yfinance 快取，確保取得最新價格
_cache = os.path.join(os.path.expanduser("~"), ".cache", "py-yfinance")
if os.path.exists(_cache):
    shutil.rmtree(_cache, ignore_errors=True)

# 元大商品代碼 → Yahoo Finance 代碼
SYMBOL_MAP = {
    "2330":   "2330.TW",
    "00631L": "00631L.TW",
    "00675L": "00675L.TW",
    "MXFB5":  "^TWII",   # 元大API開通前用加權指數近似
    "MXFD6":  "^TWII",   # 同上
    "TMF8":   "^TWII",   # 同上
    "MXFPM1": "^TWII",   # 同上
}

# 時間框架 → (yfinance interval, period, 是否需要重新取樣)
TF_CONFIG = {
    "3":  ("1m",  "5d",   3),
    "6":  ("2m",  "60d",  3),
    "15": ("15m", "60d",  1),
    "60": ("60m", "730d", 1),
    "D":  ("1d",  "5y",   1),
    "W":  ("1wk", "10y",  1),
}


def _to_candles(df: pd.DataFrame, resample_factor: int = 1) -> list:
    """將 DataFrame 轉換為前端可用的 K 棒格式"""
    if df.empty:
        return []

    if resample_factor > 1:
        tf = f"{resample_factor}T"
        df = df.resample(tf).agg({
            "Open":   "first",
            "High":   "max",
            "Low":    "min",
            "Close":  "last",
            "Volume": "sum",
        }).dropna()

    candles = []
    for ts, row in df.iterrows():
        # 轉換為 Unix timestamp（秒）
        t = int(ts.timestamp())
        candles.append({
            "time":   t,
            "open":   round(float(row["Open"]),  2),
            "high":   round(float(row["High"]),  2),
            "low":    round(float(row["Low"]),   2),
            "close":  round(float(row["Close"]), 2),
        })
    return candles


async def get_history(symbol: str, tf: str) -> list:
    yahoo_sym = SYMBOL_MAP.get(symbol)
    if not yahoo_sym:
        return []

    config = TF_CONFIG.get(tf)
    if not config:
        return []

    interval, period, resample_factor = config

    try:
        ticker = yf.Ticker(yahoo_sym)
        df = ticker.history(period=period, interval=interval, auto_adjust=False)
        if df.empty:
            return []
        return _to_candles(df, resample_factor)
    except Exception as e:
        print(f"[History] {symbol} {tf} 抓取失敗: {e}")
        return []
