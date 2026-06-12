"""證交所 MIS 即時行情快照（mis.twse.com.tw）。

非官方公開介面、免金鑰。一次請求可帶多檔股票，
全市場約 1000 檔上市普通股分批抓，一輪約 20 秒。
請求太頻繁會被封 IP，批次之間固定 sleep。
"""
import time

import pandas as pd
import requests

BATCH = 80
SLEEP = 1.2

HEADERS = {
    "User-Agent": "Mozilla/5.0 (stock-tide intraday)",
    "Referer": "https://mis.twse.com.tw/stock/fibest.jsp",
}


class MisProvider:
    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        # 先踩一次首頁拿 session cookie，否則 API 可能回空
        try:
            self._session.get("https://mis.twse.com.tw/stock/index.jsp", timeout=15)
        except requests.RequestException:
            pass

    def fetch_index(self) -> float | None:
        """加權指數當日漲跌幅（%），當作「大盤」基準。"""
        q = self.fetch_index_quote()
        return q["chg"] if q else None

    def fetch_index_quote(self) -> dict | None:
        """加權指數即時報價：last/prev_close/open/high/low/chg。"""
        url = ("https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
               "?ex_ch=tse_t00.tw&json=1&delay=0")
        try:
            m = self._session.get(url, timeout=15).json()["msgArray"][0]
            z, y = float(m["z"]), float(m["y"])
            return {
                "last": z, "prev_close": y,
                "open": _num(m.get("o")), "high": _num(m.get("h")),
                "low": _num(m.get("l")),
                "chg": (z / y - 1) * 100,
            }
        except Exception:
            return None

    def fetch_snapshot(self, codes: list[str]) -> pd.DataFrame:
        """回傳 DataFrame：code, name, price, prev_close, acc_shares（股）。

        price 取最新成交價；尚無成交時退而求其次用買價/昨收。
        """
        rows = []
        for i in range(0, len(codes), BATCH):
            batch = codes[i:i + BATCH]
            ex_ch = "|".join(f"tse_{c}.tw" for c in batch)
            url = ("https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
                   f"?ex_ch={ex_ch}&json=1&delay=0")
            try:
                data = self._session.get(url, timeout=15).json()
            except (requests.RequestException, ValueError):
                time.sleep(SLEEP)
                continue
            for s in data.get("msgArray", []):
                price = _num(s.get("z")) or _num(s.get("b", "").split("_")[0]) \
                    or _num(s.get("y"))
                prev = _num(s.get("y"))
                vol = _num(s.get("v"))  # 累計成交量（張）
                if not price or not prev or vol is None:
                    continue
                rows.append({
                    "code": s["c"],
                    "name": s.get("n", s["c"]),
                    "price": price,
                    "prev_close": prev,
                    "acc_shares": vol * 1000,
                    "open": _num(s.get("o")),
                    "high": _num(s.get("h")),
                    "low": _num(s.get("l")),
                })
            time.sleep(SLEEP)
        return pd.DataFrame(rows)


def _num(v) -> float | None:
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None
