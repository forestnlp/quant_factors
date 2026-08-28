# -*- coding: utf-8 -*-
"""TPD红柱放大 — 交易成本敏感性分析（实验区）

对最优参数(M=6,N=12,vol_thr=1.2)在全样本回测，逐笔扣除双边成本：
    cost = 买入佣金 + 卖出佣金 + 买入滑点 + 卖出滑点
分多档成本水平考察累计收益，判断策略在高频薄利下是否仍可行。
"""
from pathlib import Path
import numpy as np
import pandas as pd

DATA_CSV = Path("/home/chinapost/users/jaycode/quant_factors/data/bt_export/513310_5min.csv")
M, N, VOL_THR = 6, 12, 1.2


def get_signals(df):
    """返回全部交易信号：(date, buy_price, sell_price)。"""
    all_trades = []
    for _, day in df.groupby("date"):
        if len(day) < N + 15:
            continue
        typ = (day["开盘"] + day["收盘"]) / 2
        close = day["收盘"]
        tpd = close.ewm(span=M, adjust=False).mean() - typ.ewm(span=M, adjust=False).mean()
        matpd = tpd.rolling(N).mean()
        bar = tpd - matpd
        expanding = bar > bar.shift(1)
        vol_base = day["成交量"].astype(float).rolling(10).mean()
        vol_ratio = day["成交量"].astype(float) / vol_base.replace(0, np.nan)

        opens = day["开盘"].values; closes = day["收盘"].values
        bars = bar.values; expand = expanding.values; vr = vol_ratio.values
        pos = False; entry = 0.0
        for i in range(len(day)):
            ok = bool(bars[i] > 0 and expand[i]) and (vr[i] == vr[i] and vr[i] > VOL_THR)
            if not pos and i > 0 and ok:
                pos = True; entry = opens[i]
            elif pos:
                fc = (i == len(day)-1) or (bars[i] < 0)
                if fc:
                    all_trades.append((entry, closes[i]))
                    pos = False
    return all_trades


def main():
    df = pd.read_csv(DATA_CSV, parse_dates=["时间"])
    df["date"] = df["时间"].dt.date
    trades = get_signals(df)
    n_days = df["date"].nunique()

    # 成本档位：单边费率（佣金+滑点合计）
    cost_levels = {
        "零成本(理想)": 0.0000,
        "低(万5/边)": 0.0005,
        "中(万10/边)": 0.0010,
        "高(万15/边)": 0.0015,
    }

    print(f"参数 M={M}, N={N}, vol_thr={VOL_THR} | {n_days}交易日 | {len(trades)}笔交易\n")
    print(f"{'成本档':<16}{'单边费':>8}{'累计收益':>12}{'复利累计':>12}{'年化':>12}")
    print("-" * 62)

    results = {}
    for name, fee in cost_levels.items():
        rets = [sell / buy - 1 - 2*fee for buy, sell in trades]
        simple = sum(rets)
        geo = np.prod([1+r for r in rets]) - 1
        annual = (1+geo) ** (242/n_days) - 1
        results[name] = (simple, geo, annual)
        print(f"{name:<16}{fee*10000:>7.1f}‰{simple:>11.2%}{geo:>11.2%}{annual:>11.2%}")

    # 盈亏平衡：多少单边成本会吃掉全部利润
    total_gross = sum(sell/buy - 1 for buy, sell in trades)
    breakeven = total_gross / len(trades) / 2 if trades else 0
    print("\n" + "=" * 46)
    print(f"毛利合计: {total_gross:.2%}, 共{len(trades)}笔")
    print(f"盈亏平衡单边费率(约): {breakeven*10000:.1f}‰/边")
    print("（若真实单边成本高于该值，策略将转为亏损）")

if __name__ == "__main__":
    main()
