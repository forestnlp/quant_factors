# -*- coding: utf-8 -*-
"""中韩半导体ETF(513310) 5分钟 — TPD「红柱放大」趋势加速日内 T+0（实验区）

思路：把 TPD 改造成类似 MACD 红柱放大的「趋势加速确认」信号。
    类比：TPD~DIF，MATPD~DEA，BAR = TPD - MATPD ~ MACD 柱。
    - 买入：BAR > 0 且 BAR 较上一根递增（红柱放大=多头动能增强），并可叠加量比过滤
    - 卖出：BAR 转为 < 0（红翻绿）或收盘强制平仓（纯日内不过夜）

每个周期组合都做：参数扫描 + 前段20天选参 / 后段11天样本外验证。
数据来源：data/bt_export/513310_5min.csv
用法：
    conda run -n jaycode python playground/tpd_macd_bar.py

成功标准：
    脚本无异常退出，输出前段最优参数及样本外表现。
"""

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_CSV = PROJECT_ROOT / "data" / "bt_export" / "513310_5min.csv"


def backtest_day(day: pd.DataFrame, m: int, n: int, vol_thr):
    typ = (day["开盘"] + day["收盘"]) / 2
    close = day["收盘"]

    tpd = close.ewm(span=m, adjust=False).mean() - typ.ewm(span=m, adjust=False).mean()
    matpd = tpd.rolling(n).mean()
    bar = tpd - matpd                    # 类比 MACD 柱
    expanding = bar > bar.shift(1)       # 红柱放大（较上一根递增）

    if vol_thr is not None:
        vol_base = day["成交量"].astype(float).rolling(10).mean()
        vol_ratio = day["成交量"].astype(float) / vol_base.replace(0, np.nan)

    opens = day["开盘"].values
    closes = day["收盘"].values
    bars = bar.values
    expand = expanding.values
    vr_arr = vol_ratio.values if vol_thr is not None else None
    n_bar = len(day)

    pnl = 0.0
    position = False
    entry_price = 0.0
    for i in range(n_bar):
        long_ok = bool(bars[i] > 0 and expand[i])
        if vol_thr is not None:
            vr = vr_arr[i]
            long_ok = long_ok and (vr == vr and vr > vol_thr)

        if not position and i > 0 and long_ok:
            position = True
            entry_price = opens[i]
        elif position:
            force_close = (i == n_bar - 1) or (bars[i] < 0)
            if force_close:
                pnl += closes[i] / entry_price - 1
                position = False
    return pnl


def evaluate(sub_df: pd.DataFrame, m: int, n: int, vol_thr):
    pnls = []
    for _, day in sub_df.groupby("date"):
        if len(day) >= n + 15:
            pnls.append(backtest_day(day, m, n, vol_thr))
    pnls = np.array(pnls)
    total = float(pnls.sum())
    daily = total / len(pnls) if len(pnls) else np.nan
    win_rate = float((pnls > 0).mean()) if len(pnls) else np.nan
    return {"total": total, "daily": daily, "days": len(pnls), "win_rate": win_rate}


def main():
    df = pd.read_csv(DATA_CSV, parse_dates=["时间"])
    df["date"] = df["时间"].dt.date

    dates = sorted(df["date"].unique())
    split = 20
    train = df[df["date"].isin(set(dates[:split]))]
    test = df[df["date"].isin(set(dates[split:]))]
    print(f"标的: 513310 | {len(dates)} 交易日")
    print(f"前段: {len(train['date'].unique())}天 ({dates[0]}~{dates[split-1]})")
    print(f"后段: {len(test['date'].unique())}天 ({dates[split]}~{dates[-1]})\n")

    Ms = [6, 8, 12]
    Ns = [12, 24]
    vol_thrs = [None, 1.2, 1.5]

    rows = []
    for thr in vol_thrs:
        for m in Ms:
            for n in Ns:
                r = evaluate(train, m, n, thr)
                rows.append({"M": m, "N": n, "vol_thr": thr if thr else "-", **r})

    result = pd.DataFrame(rows).sort_values("daily", ascending=False)
    best_row = result.iloc[0]
    bm = int(best_row["M"])
    bn = int(best_row["N"])
    bthr = None if best_row["vol_thr"] == "-" else float(best_row["vol_thr"])

    print("前段(in-sample)扫描结果（前10，按日均收益）：")
    print(result.head(10)[["M", "N", "vol_thr", "total", "daily", "win_rate"]].round(4).to_string(index=False))

    print("\n" + "=" * 60)
    print(f"[前段最优] M={bm}, N={bn}, vol_thr={bthr if bthr else '无'}")
    oos = evaluate(test, bm, bn, bthr)
    print(f"[样本外]  累计 {oos['total']:.2%} | 日均 {oos['daily']*100:.3f}%/日 | 胜率 {oos['win_rate']:.1%} | {oos['days']}天")

    out_csv = PROJECT_ROOT / "data" / "bt_export" / "tpd_macd_bar_oos.csv"
    result.to_csv(out_csv, index=False)
    print(f"\n完整扫描表已存 -> {out_csv}")


if __name__ == "__main__":
    main()
