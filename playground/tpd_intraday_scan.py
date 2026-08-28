# -*- coding: utf-8 -*-
"""中韩半导体ETF(513310) 5分钟 TPD 纯日内 T+0 — 参数扫描 + 开仓过滤（实验区）

对 (M, N) 网格扫描，并可叠加「成交量放大」开仓过滤：
    - vol_ratio = 当前bar成交量 / 当日前若干bar平均成交量
    - 仅当 vol_ratio > thr 时才允许买入（确认有资金推动）

数据来源：data/bt_export/513310_5min.csv
用法：
    conda run -n jaycode python playground/tpd_intraday_scan.py

成功标准：
    脚本无异常退出，输出参数扫描结果表与推荐参数。
"""

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_CSV = PROJECT_ROOT / "data" / "bt_export" / "513310_5min.csv"


def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def backtest_day(day_df: pd.DataFrame, m: int, n: int, vol_thr: float | None):
    """单日纯日内回测，返回该日收益率（单利累计）。"""
    typ = (day_df["开盘"] + day_df["收盘"]) / 2
    close = day_df["收盘"]
    tpd = close.ewm(span=m, adjust=False).mean() - typ.ewm(span=m, adjust=False).mean()
    matpd = tpd.rolling(n).mean()

    # 成交量过滤：当前bar量 / 前VOL_WIN根均量
    if vol_thr is not None:
        vol_base = day_df["成交量"].rolling(10).mean()
        vol_ratio = day_df["成交量"] / vol_base

    prev_tpd = tpd.shift(1)
    prev_matpd = matpd.shift(1)
    buy_raw = (tpd > matpd) & (prev_tpd <= prev_matpd)
    if vol_thr is not None:
        buy_sig = buy_raw & (vol_ratio > vol_thr)
    else:
        buy_sig = buy_raw
    sell_sig = (tpd < matpd) & (prev_tpd >= prev_matpd)

    opens = day_df["开盘"].values
    closes = day_df["收盘"].values
    n_bar = len(day_df)

    pnl = 0.0
    position = False
    entry_price = 0.0
    for i in range(n_bar):
        if not position and i > 0 and i - 1 < len(buy_sig) and buy_sig.iloc[i - 1]:
            position = True
            entry_price = opens[i]
        elif position:
            force_close = (i == n_bar - 1) or sell_sig.iloc[i - 1]
            if force_close:
                pnl += closes[i] / entry_price - 1
                position = False
    return pnl


def evaluate(df: pd.DataFrame, m: int, n: int, vol_thr: float | None):
    """全样本评估一组参数，返回统计字典。"""
    pnls = []
    n_days = 0
    for date, day in df.groupby("date"):
        # 需要足够bar预热滚动均线/量基准
        if len(day) < n + 15:
            continue
        n_days += 1
        pnl = backtest_day(day, m, n, vol_thr)
        pnls.append(pnl)

    pnls = np.array(pnls)
    total = float(pnls.sum())
    win_rate = float((pnls > 0).mean()) if len(pnls) else np.nan
    avg_win = float(pnls[pnls > 0].mean()) if (pnls > 0).any() else np.nan
    avg_loss = float(pnls[pnls <= 0].mean()) if (pnls <= 0).any() else np.nan
    return {
        "M": m, "N": n,
        "vol_thr": vol_thr if vol_thr is not None else "-",
        "days": n_days,
        "total": total,
        "daily": total / n_days if n_days else np.nan,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }


def main() -> None:
    df = pd.read_csv(DATA_CSV, parse_dates=["时间"])
    df["date"] = df["时间"].dt.date

    # 参数网格
    Ms = [6, 8, 12, 16]
    Ns = [12, 24, 36]
    vol_thrs = [None, 1.2, 1.5]

    print(f"标的: 513310 | {df['date'].nunique()} 交易日 | 参数扫描 M={Ms}, N={Ns}, vol={[v or '无' for v in vol_thrs]}")
    print("=" * 78)

    rows = []
    best = None
    for thr in vol_thrs:
        for m in Ms:
            for n in Ns:
                r = evaluate(df, m, n, thr)
                rows.append(r)
                if best is None or (r["daily"] > best["daily"] and not np.isnan(r["daily"])):
                    best = r

    result = pd.DataFrame(rows).sort_values("daily", ascending=False)
    print("\n扫描结果（按日均收益降序，前 20）：")
    print(result.head(20)[["M", "N", "vol_thr", "days", "total", "daily", "win_rate", "avg_win", "avg_loss"]].round(4).to_string(index=False))

    print("\n" + "=" * 78)
    print(f"最优参数: M={best['M']}, N={best['N']}, vol_thr={best['vol_thr']}")
    print(f"  累计收益: {best['total']:.2%} | 日均: {best['daily']*100:.3f}%/日 | 胜率: {best['win_rate']:.1%}")

    out_csv = PROJECT_ROOT / "data" / "bt_export" / "tpd_intraday_scan.csv"
    result.to_csv(out_csv, index=False)
    print(f"\n完整扫描表已存 -> {out_csv}")


if __name__ == "__main__":
    main()
