"""Yahoo Finance 免費價量資料源（美股 / 未來全球市場通用）。"""
import pandas as pd
import yfinance as yf

from .base import PriceProvider


class YahooProvider(PriceProvider):
    def fetch_prices(self, symbols: list[str], lookback_days: int) -> pd.DataFrame:
        data = yf.download(
            symbols,
            period=f"{lookback_days}d",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        close = data["Close"]
        if isinstance(close, pd.Series):  # 單一 symbol 時 yf 回 Series
            close = close.to_frame(symbols[0])
        return close.dropna(how="all")
