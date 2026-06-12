"""每日資料管線：抓資料 → 算指標 → 輸出 public/data/*.json

用法：
    python pipeline/run.py          # 全部市場
    python pipeline/run.py tw       # 只跑台股
    python pipeline/run.py us       # 只跑美股
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.indicators.flow import compute_sector_flow
from pipeline.indicators.rrg import compute_rrg
from pipeline.providers.twse import TwseProvider
from pipeline.providers.yahoo import YahooProvider

DATA_DIR = Path(__file__).resolve().parent.parent / "public" / "data"

# 美股 11 大 SPDR 類股 ETF，基準 SPY。
# 之後要「導入所有股票」時，把成分股清單塞進對應 universe 即可。
US_SECTORS = {
    "XLK": "科技", "XLF": "金融", "XLV": "醫療保健", "XLE": "能源",
    "XLI": "工業", "XLY": "非必需消費", "XLP": "必需消費", "XLB": "原物料",
    "XLU": "公用事業", "XLRE": "房地產", "XLC": "通訊服務",
}
US_BENCHMARK = "SPY"


def _write(name: str, payload: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload["generatedAt"] = datetime.now(timezone.utc).isoformat()
    out = DATA_DIR / f"{name}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"  -> {out} ({len(payload['sectors'])} sectors)")


def run_tw():
    print("[TW] 抓取 TWSE 三大法人買賣超（約 30 個交易日，首次較久）...")
    provider = TwseProvider()
    flows = provider.fetch_flows(days=30)
    sectors = compute_sector_flow(flows)
    _write("tw", {
        "market": "tw",
        "title": "台股｜三大法人資金輪動",
        "mode": "flow",
        "unit": "億元",
        "axisX": "近5日法人買賣超",
        "axisY": "資金加速度（近5日 − 前5日）",
        "dataDate": provider.latest_date(),
        "sectors": sectors,
    })


def run_us():
    print("[US] 抓取美股類股 ETF 價格，計算 RRG...")
    provider = YahooProvider()
    symbols = list(US_SECTORS) + [US_BENCHMARK]
    close = provider.fetch_prices(symbols, lookback_days=250)
    sectors = compute_rrg(close, US_BENCHMARK, US_SECTORS)
    _write("us", {
        "market": "us",
        "title": "美股｜類股相對輪動（RRG vs SPY）",
        "mode": "rrg",
        "unit": "",
        "axisX": "相對強度（RS-Ratio）",
        "axisY": "相對動能（RS-Momentum）",
        "dataDate": str(close.index[-1].date()),
        "sectors": sectors,
    })


if __name__ == "__main__":
    targets = sys.argv[1:] or ["tw", "us"]
    if "tw" in targets:
        run_tw()
    if "us" in targets:
        run_us()
    print("完成。")
