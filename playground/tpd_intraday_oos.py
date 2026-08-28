# -*- coding: utf-8 -*-
"""中韩半导体ETF(513310) 5分钟 TPD 纯日内 — 样本外验证（实验区）

目的：检验「全样本挑出的最优参数」是否过拟合。
做法：
    1. 将 31 个交易日按时间分成：前段(in-sample) 20 天 / 后段(out-of-sample) 11 天
    2. 只在前段做参数网格扫描，选出最优 (M, N, vol_thr)
    3. 把该最优参数用到后段（样本外）独立回测
若后段仍能保持正收益 → 说明非纯运气；否则提示过拟合风险。

数据来源：data/bt_export/513310_5min.csv
用法：
    conda run -n jaycode python playground/tpd_intraday_oos.py

成功标准：
    脚本无异常退出，输出前段最优参数及该参数在样本外的表现。
"""

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_CSV = PROJECT_ROOT / "data" / "bt_export" / "513310_5min.csv"


def backtest_day(day_df: pd.DataFrame, m: int, n: int, vol_thr: float | None):
    """单日纯日内回测，返回该日收益率。"""
    typ = (day_df["开盘"] + day_df["收盘"]) / 2
    close = day_df["收盘"]
    tpd = close.ewm(span=m, adjust=False).mean() - typ.ewm(span=m, adjust=False).mean()
    matpd = tpd.rolling(n).mean()

    if vol_thr is not None:
        vol_base = day_df["成交量"].rolling(10).mean()
        vol_ratio = day_df["成交量"] / vol_base

    prev_tpd = tpd.shift(1)
    prev_matpd = matpd.shift(1)
    buy_raw = (tpd > matpd) & (prev_tpd <= prev_matpd)
    buy_sig = buy_raw if vol_thr is None else buy_raw & (vol_ratio > vol_thr)
    sell_sig = (tpd < matpd) & (prev_tpd >= prev_matpd)

    opens = day_df["开盘"].values
    closes = day_df["收盘"].values
    n_bar = len(day_df)

    pnl = 0.0
    position = False
    entry_price = 0.0
    for i in range(n_bar):
        if not position and i > 0 and buy_sig.iloc[i - 1]:
            position = True
            entry_price = opens[i]
        elif position:
            force_close = (i == n_bar - 1) or sell_sig.iloc[i - 1]
            if force_close:
                pnl += closes[i] / entry_price - 1
                position = False
    return pnl


def evaluate(sub_df: pd.DataFrame, m: int, n: int, vol_thr: float | None):
    """在子样本上评估一组参数，返回 (日均收益, 累计, 天数)。"""
    pnls = []
    n_days = 0
    for _, day in sub_df.groupby("date"):
        if len(day) < n + 15:
            continue
        n_days += 1
        pnls.append(backtest_day(day, m, n, vol_thr))
    pnls = np.array(pnls)
    total = float(pnls.sum())
    daily = total / n_days if n_days else np.nan
    win_rate = float((pnls > 0).mean()) if len(pnls) else np.nan
    return {"daily": daily, "total": total, "days": n_days, "win_rate": win_rate}


def main() -> None:
    df = pd.read_csv(DATA_CSV, parse_dates=["时间"])
    df["date"] = df["时间"].dt.date

    dates = sorted(df["date"].unique())
    split = 20
    train_dates = set(dates[:split])
    test_dates = set(dates[split:])
    train = df[df["date"].isin(train_dates)]
    test = df[df["date"].isin(test_dates)]
    print(f"前段(in-sample): {len(train_dates)}天 ({dates[0]}~{dates[split-1]})")
    print(f"后段(out-of-sample): {len(test_dates)}天 ({dates[split]}~{dates[-1]})\n")

    # ---- 仅在前段选参 ----
    Ms = [6, 8, 12, 16]
    Ns = [12, 24, 36]
    vol_thrs = [None, 1.2, 1.5]
    best = None
    for thr in vol_thrs:
        for m in Ms:
            for n in Ns:
                r = evaluate(train, m, n, thr)
                if best is None or (r["daily"] > best["daily"] and not np.isnan(r["daily"])):
                    best = {"M": m, "N": n, "vol_thr": thr, **r}

    print("前段最优参数:", f"M={best['M']}, N={best['N']}, vol_thr={best['vol_thr']}")
    print(f"  前段表现: 累计 {best['total']:.2%} | 日均 {best['daily']*100:.3f}%/日 | 胜率 {best['win_rate']:.1%}\n")

    # ---- 用前段最优参数做样本外验证 ----
    oos = evaluate(test, best["M"], best["N"], best["vol_thr"])
    print("=" * 60)
    print("样本外(out-of-sample)验证结果")
    print("=" * 60)
    print(f"  参数沿用前段最优 M={best['M']}, N={best['N']}, vol_thr={best['vol_thr']}")
    print(f"  样本外天数: {oos['days']}")
    print(f"  累计收益: {oos['total']:.2%}")
    print(f"  日均收益: {oos['daily']*100:.3f}%/日")
    print(f"  胜率: {oos['win_rate']:.1%}")

    # 逐日明细（样本外）
    print("\n样本外逐日:")
    for _, day in test.groupby("date"):
        pnl = backtest_day(day, best["M"], best["N"], best["vol_thr"])
        if len(day) >= best["N"] + 15:
            print(f"  {day['date'].iloc[0]}  {pnl:+.4f}  ({pnl*100:+.3f}%)")


if __name__ == "__main__":
    main()
