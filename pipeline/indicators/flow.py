"""台股法人資金流輪動指標（Tide 同款邏輯）。

每個板塊：
- x = 近 5 日法人買賣超金額（億元）
- y = 加速度 = 近 5 日 − 前 5 日（億元）
- size = 近 20 日累計買賣超金額絕對值
- phase: 漲潮(x>0,y>0) / 輪動(x>0,y<=0) / 觀望(x<=0,y>0) / 退潮(x<=0,y<=0)
"""
import pandas as pd

E8 = 1e8  # 億


def classify(x: float, y: float) -> str:
    if x > 0:
        return "rising" if y > 0 else "rotating"
    return "watching" if y > 0 else "ebbing"


def compute_sector_flow(flows: pd.DataFrame) -> list[dict]:
    """flows: date, code, name, sector, net_amount（依日期不限順序）"""
    dates = sorted(flows["date"].unique())
    daily = (flows.groupby(["sector", "date"])["net_amount"]
             .sum().unstack(fill_value=0).reindex(columns=dates, fill_value=0))

    last5 = daily.iloc[:, -5:].sum(axis=1)
    prev5 = daily.iloc[:, -10:-5].sum(axis=1)
    last20 = daily.iloc[:, -20:].sum(axis=1)

    # 個股明細：近 5 日買賣超前後各 5 名
    recent = flows[flows["date"].isin(dates[-5:])]
    stock5 = (recent.groupby(["sector", "code", "name"])["net_amount"]
              .sum().reset_index())

    out = []
    for sector in daily.index:
        x = last5[sector] / E8
        y = (last5[sector] - prev5[sector]) / E8
        s = stock5[stock5["sector"] == sector].sort_values(
            "net_amount", ascending=False)
        top = s.head(5)
        bottom = s.tail(5).iloc[::-1]
        out.append({
            "name": sector,
            "x": round(x, 2),
            "y": round(y, 2),
            "size": round(abs(last20[sector]) / E8, 2),
            "flow20": round(last20[sector] / E8, 2),
            "phase": classify(x, y),
            "topBuy": [
                {"code": r.code, "name": r.name, "amount": round(r.net_amount / E8, 2)}
                for r in top.itertuples() if r.net_amount > 0],
            "topSell": [
                {"code": r.code, "name": r.name, "amount": round(r.net_amount / E8, 2)}
                for r in bottom.itertuples() if r.net_amount < 0],
        })
    return out
