# -*- coding: utf-8 -*-
"""中韩半导体ETF(513310) 5分钟 — TPD红柱放大 交易明细（实验区）

用最优参数(M=6,N=12,vol_thr=1.2)跑全样本，输出每笔交易明细、每日汇总，并导出信号CSV。
数据来源：data/bt_export/513310_5min.csv
用法：
    conda run -n jaycode python playground/tpd_macd_bar_detail.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_CSV = PROJECT_ROOT / "data" / "bt_export" / "513310_5min.csv"

M = 6
N = 12
VOL_THR = 1.2


def backtest_day(day: pd.DataFrame, m: int, n: int, vol_thr):
    """单日回测，返回 (该日收益率, 交易列表)。"""
    typ = (day["开盘"] + day["收盘"]) / 2
    close = day["收盘"]

    tpd = close.ewm(span=m, adjust=False).mean() - typ.ewm(span=m, adjust=False).mean()
    matpd = tpd.rolling(n).mean()
    bar = tpd - matpd
    expanding = bar > bar.shift(1)

    vol_base = day["成交量"].astype(float).rolling(10).mean()
    vol_ratio = day["成交量"].astype(float) / vol_base.replace(0, np.nan)

    opens = day["开盘"].values
    closes = day["收盘"].values
    times = day["时间"].dt.strftime("%H:%M").values
    dates = day["date"].astype(str).values
    bars = bar.values
    expand = expanding.values
    vr_arr = vol_ratio.values

    trades = []
    pnl = 0.0
    position = False
    entry_price = 0.0
    entry_time = None
    entry_date = None
    n_bar = len(day)

    for i in range(n_bar):
        long_ok = bool(bars[i] > 0 and expand[i])
        vr = vr_arr[i]
        long_ok = long_ok and (vr == vr and vr > vol_thr)

        if not position and i > 0 and long_ok:
            position = True
            entry_price = opens[i]
            entry_time = times[i]
            entry_date = dates[i]
        elif position:
            force_close = (i == n_bar - 1) or (bars[i] < 0)
            if force_close:
                ret = closes[i] / entry_price - 1
                pnl += ret
                trades.append({
                    "date": entry_date, "buy_time": entry_time, "buy_price": entry_price,
                    "sell_time": times[i], "sell_price": closes[i], "ret": ret,
                })
                position = False
    return pnl, trades


def main():
    df = pd.read_csv(DATA_CSV, parse_dates=["时间"])
    df["date"] = df["时间"].dt.date

    all_trades = []
    per_day = []
    for date, day in df.groupby("date"):
        if len(day) >= N + 15:
            pnl, trades = backtest_day(day, M, N, VOL_THR)
            per_day.append({"date": date, "n_trades": len(trades), "daily_pnl": pnl})
            all_trades += trades

    print(f"标的: 513310 | 最优参数 M={M}, N={N}, vol_thr={VOL_THR}")
    print("=" * 70)

    trades_df = pd.DataFrame(all_trades)
    print(f"\n总交易笔数: {len(trades_df)}")
    print("\n近 20 笔交易明细（按时间倒序）：")
    if len(trades_df):
        print(trades_df.tail(20)[["date", "buy_time", "buy_price", "sell_time", "sell_price", "ret"]]
              .round(4).to_string(index=False))

    print("\n" + "-" * 40)
    print("每日汇总（全部交易日）：")
    per_day_df = pd.DataFrame(per_day)
    print(per_day_df.to_string(index=False))

    total = float(per_day_df["daily_pnl"].sum())
    win_days = (per_day_df["daily_pnl"] > 0).sum()
    print("\n" + "=" * 60)
    print(f"累计收益(单利): {total:.2%}")
    print(f"盈利天数: {win_days}/{len(per_day_df)} ({win_days/len(per_day_df):.1%})")

    # 导出信号表
    out_csv = PROJECT_ROOT / "data" / "bt_export" / "tpd_macd_bar_trades.csv"
    if len(trades_df):
        trades_df.to_csv(out_csv, index=False)
        print(f"\n交易明细已存 -> {out_csv}")


if __name__ == "__main__":
    main()
