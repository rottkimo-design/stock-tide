"""台股盤中價量輪動 runner。

用法：
    python pipeline/intraday.py          # 常駐：開盤時間內每 60 秒更新一輪
    python pipeline/intraday.py --once   # 立刻跑一輪就結束（測試用）

輸出 public/data/tw_intraday.json；前端看 generatedAt 是否新鮮
決定顯示盤中版或盤後法人版。
"""
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.indicators.intraday import compute_intraday, sector_amounts
from pipeline.providers.mis import MisProvider
from pipeline.providers.twse import TwseProvider

TPE = ZoneInfo("Asia/Taipei")
CYCLE = 60          # 秒
MOMENTUM_MIN = 30   # 動能比較窗口（分鐘）
DATA_DIR = Path(__file__).resolve().parent.parent / "public" / "data"
HIST_DIR = Path(__file__).resolve().parent.parent / ".cache" / "intraday"


def market_open(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 <= t <= 13 * 60 + 35


def load_history(day: str) -> list[dict]:
    f = HIST_DIR / f"{day}.jsonl"
    if not f.exists():
        return []
    return [json.loads(line) for line in
            f.read_text(encoding="utf-8").splitlines() if line.strip()]


def ref_snapshot(history: list[dict], now: datetime) -> dict | None:
    """取最接近 MOMENTUM_MIN 分鐘前的板塊金額快照（至少要 5 分鐘前）。"""
    target = (now - timedelta(minutes=MOMENTUM_MIN)).timestamp()
    floor = (now - timedelta(minutes=5)).timestamp()
    candidates = [h for h in history if h["ts"] <= floor]
    if not candidates:
        return None
    return min(candidates, key=lambda h: abs(h["ts"] - target))["amounts"]


def load_state(day: str) -> dict:
    """跨 cycle 狀態（大盤走勢點位、個股 spark），重啟不丟。"""
    f = HIST_DIR / f"state_{day}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"index_points": [], "spark": {}}


def save_state(day: str, state: dict):
    HIST_DIR.mkdir(parents=True, exist_ok=True)
    (HIST_DIR / f"state_{day}.json").write_text(
        json.dumps(state), encoding="utf-8")


def write_index_json(now: datetime, quote: dict | None, state: dict):
    if quote:
        pts = state["index_points"]
        t = f"{now:%H:%M}"
        if not pts or pts[-1][0] != t:
            pts.append([t, round(quote["last"], 2)])
        state["last_quote"] = quote
    quote = state.get("last_quote")
    if not quote:
        return
    (DATA_DIR / "tw_index.json").write_text(json.dumps({
        "market": "tw-index",
        "title": "台股加權指數",
        "dataDate": f"{now:%Y-%m-%d}",
        "prevClose": quote["prev_close"],
        "open": quote.get("open"), "high": quote.get("high"),
        "low": quote.get("low"), "last": quote["last"],
        "chg": round(quote["chg"], 2),
        "points": state["index_points"],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False), encoding="utf-8")


def write_stocks_json(now: datetime, snap, state: dict):
    """全市場個股即時報價 + 走勢 spark（自選股監控用）。"""
    spark = state["spark"]
    stocks = {}
    for r in snap.itertuples():
        sp = spark.setdefault(r.code, [])
        sp.append(round(r.price, 2))
        if len(sp) > 400:
            del sp[:len(sp) - 400]
        stocks[r.code] = {
            "n": r.name, "z": r.price, "y": r.prev_close,
            "o": r.open, "h": r.high, "l": r.low,
            "chg": round((r.price / r.prev_close - 1) * 100, 2),
            "v": round(r.acc_shares / 1000),          # 張
            "a": round(r.acc_shares * r.price / 1e8, 1),  # 億（近似）
            "spark": sp[::5][-72:] + ([sp[-1]] if len(sp) % 5 != 1 else []),
        }
    (DATA_DIR / "tw_stocks.json").write_text(json.dumps({
        "dataDate": f"{now:%Y-%m-%d %H:%M}",
        "stocks": stocks,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False), encoding="utf-8")


def run_cycle(mis: MisProvider, industry: dict[str, str],
              state: dict) -> bool:
    now = datetime.now(TPE)
    day = f"{now:%Y%m%d}"

    snap = mis.fetch_snapshot(list(industry))
    if snap.empty:
        print(f"[{now:%H:%M}] MIS 沒回資料，跳過")
        return False
    snap["sector"] = snap["code"].map(industry)
    snap = snap.dropna(subset=["sector"])

    index_quote = mis.fetch_index_quote()
    history = load_history(day)
    sectors, market_chg = compute_intraday(
        snap, ref_snapshot(history, now),
        index_quote["chg"] if index_quote else None)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "tw_intraday.json").write_text(json.dumps({
        "market": "tw",
        "title": "台股｜盤中價量輪動",
        "mode": "intraday",
        "unit": "%",
        "axisX": "相對大盤漲跌幅",
        "axisY": f"資金動能（近{MOMENTUM_MIN}分占比 − 全日占比）",
        "dataDate": f"{now:%Y-%m-%d %H:%M}",
        "marketChg": market_chg,
        "sectors": sectors,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False), encoding="utf-8")

    write_index_json(now, index_quote, state)
    write_stocks_json(now, snap, state)
    save_state(day, state)

    HIST_DIR.mkdir(parents=True, exist_ok=True)
    with open(HIST_DIR / f"{day}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now.timestamp(),
                            "amounts": sector_amounts(snap)}) + "\n")
    print(f"[{now:%H:%M}] 更新完成：{len(sectors)} 板塊、"
          f"{len(snap)} 檔個股、大盤 {market_chg:+.2f}%")
    return True


def main():
    once = "--once" in sys.argv
    print("載入產業別對照表...")
    industry = TwseProvider()._industry_map()
    mis = MisProvider()
    state = load_state(f"{datetime.now(TPE):%Y%m%d}")

    if once:
        run_cycle(mis, industry, state)
        return

    print("盤中模式啟動（開盤時間 09:00–13:35 每分鐘更新）")
    while True:
        now = datetime.now(TPE)
        if market_open(now):
            start = time.time()
            try:
                run_cycle(mis, industry, state)
            except Exception as e:
                print(f"[{now:%H:%M}] 失敗：{e}")
            time.sleep(max(5, CYCLE - (time.time() - start)))
        else:
            if now.hour >= 14:
                print("已收盤，結束。明天再啟動即可（或交給排程）。")
                return
            time.sleep(60)


if __name__ == "__main__":
    main()
