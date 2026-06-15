"""台灣證交所（TWSE）免費資料源。

- T86：每日全市場個股三大法人買賣超（股數）
- STOCK_DAY_ALL：全市場個股最新收盤價（用來把股數換算成金額的近似值）
- t187ap03_L：上市公司基本資料（產業別代碼）

金額 = 買賣超股數 × 最新收盤價，是近似值（未逐日取價），
對 5/20 日的相對輪動判斷已足夠。
"""
import json
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from .base import FlowProvider

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "twse"

HEADERS = {"User-Agent": "Mozilla/5.0 (stock-tide pipeline)"}

# TWSE 產業別代碼 → 名稱
INDUSTRY_MAP = {
    "01": "水泥", "02": "食品", "03": "塑膠", "04": "紡織纖維",
    "05": "電機機械", "06": "電器電纜", "08": "玻璃陶瓷", "09": "造紙",
    "10": "鋼鐵", "11": "橡膠", "12": "汽車", "14": "建材營造",
    "15": "航運", "16": "觀光餐旅", "17": "金融保險", "18": "貿易百貨",
    "19": "綜合", "20": "其他", "21": "化學", "22": "生技醫療",
    "23": "油電燃氣", "24": "半導體", "25": "電腦及週邊設備", "26": "光電",
    "27": "通信網路", "28": "電子零組件", "29": "電子通路", "30": "資訊服務",
    "31": "其他電子", "32": "文化創意", "33": "農業科技", "34": "電子商務",
    "35": "綠能環保", "36": "數位雲端", "37": "運動休閒", "38": "居家生活",
}


class TwseProvider(FlowProvider):
    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._industry = None
        self._close = None
        self._names: dict[str, str] = {}
        self._latest = None

    # ---------- public ----------

    def fetch_flows(self, days: int) -> pd.DataFrame:
        industry = self._industry_map()
        close = self._close_prices()
        frames = []
        d = date.today()
        fetched = 0
        tried = 0
        while fetched < days and tried < days * 3:
            tried += 1
            df = self._t86(d)
            d -= timedelta(days=1)
            if df is None or df.empty:
                continue
            fetched += 1
            frames.append(df)
        if not frames:
            raise RuntimeError("TWSE T86 抓不到任何資料")
        flows = pd.concat(frames, ignore_index=True)
        flows["sector"] = flows["code"].map(industry).fillna("其他")
        flows["close"] = flows["code"].map(close)
        flows = flows.dropna(subset=["close"])
        flows["net_amount"] = flows["net_shares"] * flows["close"]
        self._latest = flows["date"].max()
        return flows[["date", "code", "name", "sector", "net_amount"]]

    def latest_date(self) -> str:
        return self._latest or ""

    # ---------- internals ----------

    def _get_json(self, url: str, cache_key: str | None = None):
        if cache_key:
            f = CACHE_DIR / f"{cache_key}.json"
            if f.exists():
                return json.loads(f.read_text(encoding="utf-8"))
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        if cache_key:
            (CACHE_DIR / f"{cache_key}.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8")
        time.sleep(3)  # TWSE 對高頻請求會封 IP
        return data

    def _t86(self, d: date) -> pd.DataFrame | None:
        """單日全市場三大法人買賣超。非交易日回 None。"""
        ds = d.strftime("%Y%m%d")
        url = (f"https://www.twse.com.tw/rwd/zh/fund/T86"
               f"?date={ds}&selectType=ALLBUT0999&response=json")
        # 當天資料可能盤後才出，只快取過去日期
        cache_key = f"t86_{ds}" if d < date.today() else None
        try:
            data = self._get_json(url, cache_key)
        except Exception:
            return None
        if data.get("stat") != "OK" or not data.get("data"):
            return None
        fields = data["fields"]
        idx_code = fields.index("證券代號")
        idx_name = fields.index("證券名稱")
        idx_total = len(fields) - 1  # 最後一欄固定是「三大法人買賣超股數」
        rows = []
        for row in data["data"]:
            if len(row) <= idx_total:
                continue  # 欄數不足的列跳過
            code = row[idx_code].strip()
            if len(code) != 4 or not code.isdigit():
                continue  # 排除 ETF/權證等，只留普通股
            try:
                net = int(row[idx_total].replace(",", ""))
            except (ValueError, AttributeError):
                continue
            rows.append({"date": f"{d:%Y-%m-%d}", "code": code,
                         "name": row[idx_name].strip(), "net_shares": net})
        return pd.DataFrame(rows)

    def _close_prices(self) -> dict[str, float]:
        if self._close is None:
            data = self._get_json(
                "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
            self._close = {}
            for row in data:
                try:
                    self._close[row["Code"]] = float(row["ClosingPrice"])
                    if row.get("Name"):
                        self._names[row["Code"]] = row["Name"].strip()
                except (ValueError, KeyError):
                    continue
        return self._close

    def fetch_names(self) -> dict[str, str]:
        """全市場代號 → 股票名稱（來自 STOCK_DAY_ALL，供離線搜尋用）。"""
        self._close_prices()  # 順帶填充 _names
        return self._names

    def _industry_map(self) -> dict[str, str]:
        if self._industry is None:
            data = self._get_json(
                "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
                cache_key=f"industry_{date.today():%Y%m%d}")
            self._industry = {}
            for row in data:
                code = row.get("公司代號", "")
                ind = row.get("產業別", "")
                if code and ind in INDUSTRY_MAP:
                    self._industry[code] = INDUSTRY_MAP[ind]
        return self._industry
