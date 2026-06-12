"""台股盤中價量輪動指標。

每個板塊：
- x = 板塊漲跌幅 − 大盤漲跌幅（成交金額加權，%）
- y = 資金動能 = 近 30 分成交金額占比 − 全日成交金額占比（百分點）
      > 0 表示資金正在湧入該板塊（相對全日的力道在加強）
- size = 當日成交金額占比（%）
- 成交金額 ≈ 累計成交量 × 最新價（無 VWAP 資料的近似）

動能需要歷史快照：由 runner 傳入約 30 分鐘前的板塊金額。
只有一份快照時動能為 0（剛開盤）。
"""
import pandas as pd

E8 = 1e8


def classify(x: float, y: float) -> str:
    if x > 0:
        return "rising" if y > 0 else "rotating"
    return "watching" if y > 0 else "ebbing"


def sector_amounts(snap: pd.DataFrame) -> dict[str, float]:
    """板塊累計成交金額（供 runner 存成歷史快照）。"""
    s = snap.copy()
    s["amount"] = s["acc_shares"] * s["price"]
    return s.groupby("sector")["amount"].sum().to_dict()


def compute_intraday(snap: pd.DataFrame,
                     ref_amounts: dict[str, float] | None,
                     market_chg: float | None = None) -> list[dict]:
    """snap: code, name, price, prev_close, acc_shares, sector
    ref_amounts: 約 30 分鐘前的板塊累計金額（None = 剛開盤）
    market_chg: 大盤漲跌幅（加權指數）；抓不到時退回金額加權平均
    """
    s = snap.copy()
    s["amount"] = s["acc_shares"] * s["price"]
    s["chg"] = (s["price"] / s["prev_close"] - 1) * 100

    market_amount = s["amount"].sum()
    if market_chg is None:
        market_chg = (s["amount"] * s["chg"]).sum() / market_amount

    now_amt = s.groupby("sector")["amount"].sum()
    total_share = now_amt / market_amount * 100

    # 近 30 分增量金額占比
    if ref_amounts:
        recent = (now_amt - pd.Series(ref_amounts).reindex(now_amt.index)
                  .fillna(0)).clip(lower=0)
        recent_total = recent.sum()
        recent_share = (recent / recent_total * 100) if recent_total > 0 \
            else total_share
    else:
        recent_share = total_share  # 動能歸零

    wchg = s.groupby("sector").apply(
        lambda g: (g["amount"] * g["chg"]).sum() / g["amount"].sum(),
        include_groups=False)

    out = []
    for sector in now_amt.index:
        x = float(wchg[sector] - market_chg)
        y = float(recent_share[sector] - total_share[sector])
        g = s[s["sector"] == sector].sort_values("amount", ascending=False)
        out.append({
            "name": sector,
            "x": round(x, 2),
            "y": round(y, 2),
            "size": round(float(total_share[sector]), 2),
            "chg": round(float(wchg[sector]), 2),
            "amount": round(float(now_amt[sector]) / E8, 1),
            "phase": classify(x, y),
            "topStocks": [
                {"code": r.code, "name": r.name,
                 "chg": round(r.chg, 2), "amount": round(r.amount / E8, 1)}
                for r in g.head(5).itertuples()],
        })
    return out, round(float(market_chg), 2)
