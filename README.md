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

## 三套輪動指標

| 市場 | 指標 | X 軸 | Y 軸 | 泡泡大小 |
|------|------|------|------|----------|
| 台股（盤後） | 三大法人買賣超 | 近 5 日買賣超金額 | 加速度（近5日−前5日） | 近 20 日累計金額 |
| 台股（盤中） | 即時價量 | 相對大盤漲跌幅 | 資金動能（近30分占比−全日占比） | 當日成交金額占比 |
| 美股 | RRG vs SPY | RS-Ratio 相對強度 | RS-Momentum 相對動能 | 近 20 日報酬絕對值 |

**盤中／盤後自動切換**：前端看 `tw_intraday.json` 的 `generatedAt` 是否在 10 分鐘內 ——
開盤時段 runner 持續更新 → 顯示盤中版（每分鐘自動刷新）；收盤後資料過期 → 自動回到法人版。

**其他分頁**（資料皆由盤中 runner 產出，每分鐘更新）：
- 大盤指數：加權指數即時走勢線（runner 每分鐘記一點，存 `.cache` 重啟不丟）
- 自選股：代號/名稱雙向搜尋加入，即時監控（價格/漲跌/開高低昨收/量/金額/當日走勢），
  上方帶加權＋櫃買指數卡片；支援**自訂分組 tabs**（全部＋多分組、可新增刪除，
  加股票時加入當前分組）與**卡片拖曳排序**（每個分組各自記順序），全部存 localStorage
- 個股詳細頁（點自選股卡片開啟）：分時走勢＋均價線＋量能、五檔委買委賣、
  漲停/跌停、分時明細（每分鐘取樣）。
  內外盤比與逐筆價量分布需要 tick 級資料，免費輪詢拿不到（需券商 API 如 Fugle/Shioaji）

所有圖表支援滾輪縮放與拖曳平移。

四階段：**漲潮**（加速流入/Leading）→ **輪動**（放緩/Weakening）→ **退潮**（流出/Lagging）→ **觀望**（趨緩/Improving）。

> 台股金額為「買賣超股數 × 最新收盤價」的近似值；RRG 採社群通用近似演算法（JdK 原版未公開）。

## 使用

```bash
pip install -r requirements.txt
python pipeline/run.py        # 盤後管線：全部市場（台股首次約 3-5 分鐘，之後有快取）
python pipeline/run.py us     # 只跑美股

python pipeline/intraday.py        # 盤中常駐：開盤時間每 60 秒更新一輪（收盤自動結束）
python pipeline/intraday.py --once # 測試：立刻跑一輪

# 看圖：任何靜態伺服器即可
python -m http.server 8000 -d public
```

## 擴展到新市場

1. 在 `pipeline/run.py` 加 universe（symbol → 名稱）與基準指數，例如日股 `1306.T` vs TOPIX、港股 vs `^HSI` —— Yahoo provider 直接通用。
2. 要換付費資料源（Polygon/EODHD）時，實作 `providers/base.py` 的介面即可，上層不用改。
3. 要「導入所有個股」：把成分股清單放進 universe，RRG 對個股一樣適用（建議以板塊為單位呈現，個股放 tooltip 明細）。

## 資料源

- 台股盤後：[TWSE OpenAPI](https://openapi.twse.com.tw/)（T86 三大法人、STOCK_DAY_ALL 收盤價、t187ap03_L 產業別）— 免費，請求間隔 3 秒
- 台股盤中：證交所 MIS 行情快照（mis.twse.com.tw，非官方公開介面、免金鑰）— 約 5 秒延遲，批次間隔 1.2 秒避免封 IP
- 美股：Yahoo Finance（yfinance）— 免費

> 法人買賣超是盤後資料（每日 16:00 後公布），盤中不存在即時法人動向，
> 因此盤中版改用價量計算資金流 proxy：「盤中看價量潮汐、盤後看法人定調」。
