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


def run_cycle(mis: MisProvider, industry: dict[str, str]) -> bool:
    now = datetime.now(TPE)
    day = f"{now:%Y%m%d}"

    snap = mis.fetch_snapshot(list(industry))
    if snap.empty:
        print(f"[{now:%H:%M}] MIS 沒回資料，跳過")
        return False
    snap["sector"] = snap["code"].map(industry)
    snap = snap.dropna(subset=["sector"])

    history = load_history(day)
    sectors, market_chg = compute_intraday(
        snap, ref_snapshot(history, now), mis.fetch_index())

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

    if once:
        run_cycle(mis, industry)
        return

    print("盤中模式啟動（開盤時間 09:00–13:35 每分鐘更新）")
    while True:
        now = datetime.now(TPE)
        if market_open(now):
            start = time.time()
            try:
                run_cycle(mis, industry)
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
