# 🌊 Stock Tide — 多市場資金輪動圖

仿 [tide-tw.app](https://tide-tw.app/) 的板塊資金輪動視覺化，支援台股＋美股，架構上可擴展至全球市場。

## 架構

```
pipeline/                 # Python 資料管線（每日跑一次）
├── providers/            # 資料源抽換層
│   ├── base.py           #   FlowProvider / PriceProvider 介面
│   ├── twse.py           #   台灣證交所（免費）：T86 三大法人買賣超
│   └── yahoo.py          #   Yahoo Finance（免費）：日 K 價量
├── indicators/
│   ├── flow.py           # 台股：法人資金流（5日流向 × 加速度 × 20日累計）
│   └── rrg.py            # 美股/全球：RRG 相對輪動（RS-Ratio × RS-Momentum）
└── run.py                # 入口：抓資料 → 算指標 → 輸出 JSON

public/                   # 純靜態前端（ECharts 泡泡圖）
├── index.html
└── data/{tw,us}.json     # 管線輸出
```

## 兩套輪動指標

| 市場 | 指標 | X 軸 | Y 軸 | 泡泡大小 |
|------|------|------|------|----------|
| 台股 | 三大法人買賣超 | 近 5 日買賣超金額 | 加速度（近5日−前5日） | 近 20 日累計金額 |
| 美股 | RRG vs SPY | RS-Ratio 相對強度 | RS-Momentum 相對動能 | 近 20 日報酬絕對值 |

四階段：**漲潮**（加速流入/Leading）→ **輪動**（放緩/Weakening）→ **退潮**（流出/Lagging）→ **觀望**（趨緩/Improving）。

> 台股金額為「買賣超股數 × 最新收盤價」的近似值；RRG 採社群通用近似演算法（JdK 原版未公開）。

## 使用

```bash
pip install -r requirements.txt
python pipeline/run.py        # 全部市場（台股首次約 3-5 分鐘，之後有快取）
python pipeline/run.py us     # 只跑美股

# 看圖：任何靜態伺服器即可
python -m http.server 8000 -d public
```

## 擴展到新市場

1. 在 `pipeline/run.py` 加 universe（symbol → 名稱）與基準指數，例如日股 `1306.T` vs TOPIX、港股 vs `^HSI` —— Yahoo provider 直接通用。
2. 要換付費資料源（Polygon/EODHD）時，實作 `providers/base.py` 的介面即可，上層不用改。
3. 要「導入所有個股」：把成分股清單放進 universe，RRG 對個股一樣適用（建議以板塊為單位呈現，個股放 tooltip 明細）。

## 資料源

- 台股：[TWSE OpenAPI](https://openapi.twse.com.tw/)（T86 三大法人、STOCK_DAY_ALL 收盤價、t187ap03_L 產業別）— 免費，請求間隔 3 秒
- 美股：Yahoo Finance（yfinance）— 免費
