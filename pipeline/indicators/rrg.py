"""RRG（相對輪動圖）指標，價量通用，美股/全球市場皆適用。

JdK 原始演算法未公開，這裡採社群通用近似：
- RS        = 100 × symbol / benchmark
- RS-Ratio  = 100 + ((RS / SMA(RS, n)) − 1) × 100 標準化
- RS-Mom    = RS-Ratio 的 n 日變化率標準化

座標中心為 (100, 100)：
- Leading   (x>100, y>100) → 漲潮
- Weakening (x>100, y<100) → 輪動
- Lagging   (x<100, y<100) → 退潮
- Improving (x<100, y>100) → 觀望
"""
import pandas as pd

WINDOW = 14


def _normalize(s: pd.Series, window: int) -> pd.Series:
    mean = s.rolling(window).mean()
    std = s.rolling(window).std()
    return 100 + (s - mean) / std


def classify(x: float, y: float) -> str:
    if x > 100:
        return "rising" if y > 100 else "rotating"
    return "watching" if y > 100 else "ebbing"


def compute_rrg(close: pd.DataFrame, benchmark: str,
                names: dict[str, str], trail: int = 5) -> list[dict]:
    """close: index=date, columns=symbols（含 benchmark）"""
    out = []
    bench = close[benchmark]
    # 泡泡大小用近 20 日成交動能 proxy：20 日報酬絕對值（無金額資料時的折衷）
    ret20 = close.pct_change(20).iloc[-1]

    for sym in close.columns:
        if sym == benchmark:
            continue
        rs = 100 * close[sym] / bench
        ratio = _normalize(rs, WINDOW)
        # 動能先做 3 日平滑，否則逐日跳動太大、軌跡雜亂
        mom = _normalize(ratio.diff().rolling(3).mean(), WINDOW)
        pair = pd.concat([ratio, mom], axis=1).dropna()
        if len(pair) < trail:
            continue
        x, y = float(pair.iloc[-1, 0]), float(pair.iloc[-1, 1])
        out.append({
            "name": names.get(sym, sym),
            "symbol": sym,
            "x": round(x, 2),
            "y": round(y, 2),
            "size": round(abs(float(ret20[sym])) * 100, 2),
            "ret20": round(float(ret20[sym]) * 100, 2),
            "phase": classify(x, y),
            "trail": [[round(float(a), 2), round(float(b), 2)]
                      for a, b in pair.iloc[-trail:].values],
        })
    return out
