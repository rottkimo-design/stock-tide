"""Provider 抽換介面。

之後要換付費 API（Polygon/EODHD）時，實作同樣的介面即可，
上層 indicators / run.py 不需要改動。
"""
from abc import ABC, abstractmethod

import pandas as pd


class FlowProvider(ABC):
    """提供「每日法人資金流」的市場（目前只有台股）。"""

    @abstractmethod
    def fetch_flows(self, days: int) -> pd.DataFrame:
        """回傳 DataFrame，欄位：
        date, code, name, sector, net_amount（三大法人買賣超金額，NTD）
        """

    @abstractmethod
    def latest_date(self) -> str:
        """最新資料日期 YYYY-MM-DD。"""


class PriceProvider(ABC):
    """提供日 K 價量的市場（美股/全球，用來算 RRG）。"""

    @abstractmethod
    def fetch_prices(self, symbols: list[str], lookback_days: int) -> pd.DataFrame:
        """回傳收盤價 DataFrame，index=date、columns=symbol。"""
