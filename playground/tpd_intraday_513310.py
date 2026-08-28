# -*- coding: utf-8 -*-
"""中韩半导体ETF(513310) 5分钟 TPD 纯日内 T+0 回测（实验区）

思路：把日线 TPD 趋势择时适配到 5 分钟尺度，但约束为「纯日内、不过夜」：
    - 每日独立判断，当天开仓必须当天收盘前平仓
    - TYP := (open + close) / 2
    - TPD := EMA(close, M) - EMA(TYP, M)
    - MATPD := MA(TPD, N)
    上穿买入 / 下穿卖出；收盘强制平仓

数据来源：data/bt_export/513310_5min.csv（由 fetch_513310_min.py 生成）
用法：
    conda run -n jaycode python playground/tpd_intraday_513310.py

成功标准：
    脚本无异常退出，输出每笔交易明细与总体统计。
"""

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_CSV = PROJECT_ROOT / "data" / "bt_export" / "513310_5min.csv"

# 参数（5 分钟尺度，按经验初设，可调）
M = 12   # EMA 快线周期（≈60分钟）
N = 24   # MATPD 慢均线周期（≈120分钟）


def ema(s: pd.Series, span: int) -> pd.Series:
    """EMA（adjust=False）。"""
    return s.ewm(span=span, adjust=False).mean()


def compute_tpd(df: pd.DataFrame) -> pd.DataFrame:
    """按日计算 TPD/MATPD（每日独立，避免跨日污染）。"""
    df = df.copy()
    typ = (df["开盘"] + df["收盘"]) / 2
    df["typ_ema"] = typ.groupby(df["date"]).transform(lambda x: ema(x, M))
    df["close_ema"] = df["收盘"].groupby(df["date"]).transform(lambda x: ema(x, M))
    df["tpd"] = df["close_ema"] - df["typ_ema"]
    df["matpd"] = df["tpd"].groupby(df["date"]).transform(lambda x: x.rolling(N).mean())
    return df.dropna().reset_index(drop=True)


def backtest_day(day_df: pd.DataFrame):
    """对单日做纯日内回测，返回该日交易列表。"""
    prev_tpd = day_df["tpd"].shift(1)
    prev_matpd = day_df["matpd"].shift(1)
    buy_sig = (day_df["tpd"] > day_df["matpd"]) & (prev_tpd <= prev_matpd)
    sell_sig = (day_df["tpd"] < day_df["matpd"]) & (prev_tpd >= prev_matpd)

    opens = day_df["开盘"].values
    closes = day_df["收盘"].values
    times = day_df["时间"].dt.strftime("%H:%M").values
    n = len(day_df)

    trades = []
    position = False
    entry_price = 0.0
    entry_time = None

    for i in range(n):
        if not position and i > 0 and buy_sig.iloc[i - 1]:
            position = True
            entry_price = opens[i]
            entry_time = times[i]
        elif position:
            # 下穿信号 或 收盘强制平仓
            force_close = (i == n - 1) or sell_sig.iloc[i - 1]
            if force_close:
                trades.append((entry_time, entry_price, times[i], closes[i]))
                position = False

    return trades


def main() -> None:
    df = pd.read_csv(DATA_CSV, parse_dates=["时间"])
    df["date"] = df["时间"].dt.date
    print(f"标的: 513310 | 5分钟数据 | {df['date'].nunique()} 个交易日 | M={M}, N={N}")
    print("=" * 70)

    df = compute_tpd(df)
    all_trades = []
    per_day = []

    for date, day in df.groupby("date"):
        t = backtest_day(day)
        daily_pnl = sum(s / b - 1 for _, b, _, s in t)
        per_day.append({"date": date, "n_trades": len(t), "daily_pnl": daily_pnl})
        all_trades += [(date, *tr) for tr in t]

    per_day_df = pd.DataFrame(per_day)
    wins = per_day_df[per_day_df["daily_pnl"] > 0]
    losses = per_day_df[per_day_df["daily_pnl"] <= 0]

    # 打印最近 10 个交易日的逐日结果
    print("\n近 10 个交易日逐日统计:")
    print(per_day_df.tail(10).to_string(index=False))

    n_days = len(per_day_df)
    total_pnl = float(per_day_df["daily_pnl"].sum())
    win_days = len(wins)
    avg_win = float(wins["daily_pnl"].mean()) if len(wins) else np.nan
    avg_loss = float(losses["daily_pnl"].mean()) if len(losses) else np.nan

    print("\n" + "=" * 70)
    print("总体统计（纯日内 T+0，单利累计）")
    print("=" * 70)
    print(f"  有效交易日: {n_days}")
    print(f"  总交易笔数: {len(all_trades)}")
    print(f"  累计收益(单利): {total_pnl:.2%}")
    print(f"  日均收益: {total_pnl / n_days:.4f} ({total_pnl / n_days * 100:.3f}%/日)")
    print(f"  盈利天数: {win_days}/{n_days} ({win_days / n_days:.1%})")
    print(f"  平均盈利用日: {avg_win:+.3%}")
    print(f"  平均亏损用日: {avg_loss:+.3%}")


if __name__ == "__main__":
    main()
