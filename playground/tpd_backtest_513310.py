# -*- coding: utf-8 -*-
"""中韩半导体ETF(513310) 的 TPD 趋势择时回测（实验区）

复用 compare_tpd_factors.py 里已验证的公式2参数，仅将标的换成 513310：

    TYP   := (open + close) / 2
    TPD   := EMA(close, M) - EMA(TYP, M)
    MATPD := MA(TPD, N)
    参数 M=7, N=6

交易规则（与现有一致，无未来函数）：
    - TPD 上穿 MATPD 当日收盘产生买入信号，次一交易日开盘价买入
    - TPD 下穿 MATPD 当日收盘产生卖出信号，次一交易日开盘价卖出
    - 期末仍持仓按最后收盘平仓

输出：交易明细 + 汇总统计，并与「买入持有」对比。

数据来源：data/bt_export/513310_daily.csv（由 fetch_513310.py 生成）

用法：
    conda run -n jaycode python playground/tpd_backtest_513310.py

成功标准：
    脚本无异常退出，打印策略 vs 买入持有的收益、胜率、最大回撤。
"""

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ---------- 配置 ----------
DATA_CSV = PROJECT_ROOT / "data" / "bt_export" / "513310_daily.csv"

M = 7   # EMA 周期
N = 6   # MATPD 均线周期


def load_data() -> pd.DataFrame:
    """读取本地 CSV，返回带 date 索引的 OHLC DataFrame。"""
    df = pd.read_csv(DATA_CSV, parse_dates=["date"])
    return df.set_index("date").sort_index()


def ema(s: pd.Series, span: int) -> pd.Series:
    """EMA（用 adjust=False 等价于通达信 EMA）。"""
    return s.ewm(span=span, adjust=False).mean()


def compute_tpd(df: pd.DataFrame) -> pd.DataFrame:
    """计算 TYP/TPD/MATPD，返回拼接后的副本。"""
    df = df.copy()
    typ = (df["open"] + df["close"]) / 2
    df["tpd"] = ema(df["close"], M) - ema(typ, M)
    df["matpd"] = df["tpd"].rolling(N).mean()
    return df.dropna()


def backtest(df: pd.DataFrame):
    """向量化择时回测，返回(交易明细, 策略每日权益序列)。"""
    prev_tpd = df["tpd"].shift(1)
    prev_matpd = df["matpd"].shift(1)
    buy_sig = (df["tpd"] > df["matpd"]) & (prev_tpd <= prev_matpd)   # 上穿
    sell_sig = (df["tpd"] < df["matpd"]) & (prev_tpd >= prev_matpd)  # 下穿

    open_ = df["open"].values
    close = df["close"].values
    dates = df.index
    n = len(df)

    trades = []          # (buy_date, buy_price, sell_date, sell_price)
    position = False
    entry_price = 0.0
    entry_date = None

    # 持仓状态序列（用于算权益曲线）
    in_position = np.zeros(n, dtype=bool)

    for i in range(n):
        if i > 0 and buy_sig.iloc[i - 1] and not position:
            position = True
            entry_price = open_[i]
            entry_date = dates[i]
        elif i > 0 and sell_sig.iloc[i - 1] and position:
            trades.append((entry_date, entry_price, dates[i], open_[i]))
            position = False
        if position:
            in_position[i] = True

    # 期末仍持仓：按最后收盘平仓（虚拟）
    if position:
        trades.append((entry_date, entry_price, dates[-1], close[-1]))
        in_position[-1] = True

    # 结构化为交易信号表：每笔含买入时刻/价、卖出时刻/价、方向、收益
    signals = pd.DataFrame(
        [
            {
                "side": "BUY",
                "datetime": bd,
                "price": bp,
                "reason": "TPD上穿MATPD",
            }
            for bd, bp, _, _ in trades
        ]
        + [
            {
                "side": "SELL",
                "datetime": sd,
                "price": sp,
                "reason": "TPD下穿MATPD",
            }
            for _, _, sd, sp in trades
        ]
    ).sort_values("datetime").reset_index(drop=True)
    signals["datetime"] = signals["datetime"].astype(str)

    return trades, in_position, signals


def max_drawdown(equity: pd.Series) -> float:
    """最大回撤。"""
    peak = equity.cummax()
    dd = equity / peak - 1
    return float(dd.min())


def summarize(trades: list, df: pd.DataFrame, in_position: np.ndarray) -> dict:
    """汇总策略统计，并与买入持有对比。"""
    rets = [sell / buy - 1 for _, buy, _, sell in trades]
    wins = [r for r in rets if r > 0]

    # 策略权益曲线：每日 = 1 + 累计已实现收益（持仓期间不逐日标记，简化为交易层面收益）
    cum_ret = np.prod([1 + r for r in rets]) - 1

    # 买入持有：区间首开到尾收
    bh = df["close"].iloc[-1] / df["open"].iloc[0] - 1

    # 策略权益序列（用于最大回撤）：逐日按当日是否持仓累乘
    daily_ret = df["close"].pct_change().fillna(0)
    strat_daily = np.where(in_position, daily_ret.values, 0.0)
    equity = pd.Series(strat_daily).add(1).cumprod()

    gross_profit = sum(r for r in rets if r > 0)
    gross_loss = abs(sum(r for r in rets if r <= 0))

    n_trades = len(trades)
    win_rate = len(wins) / n_trades if n_trades else float("nan")
    profit_loss = (gross_profit / max(len(wins), 1)) / (gross_loss / max(n_trades - len(wins), 1)) if wins and gross_loss > 0 else float("nan")

    return {
        "交易次数": n_trades,
        "胜率": win_rate,
        "策略累计收益": cum_ret,
        "买入持有收益": bh,
        "盈亏比": profit_loss,
        "策略最大回撤": max_drawdown(equity),
        "买入持有最大回撤": max_drawdown(df["close"] / df["close"].iloc[0]),
        "持仓占比": float(in_position.mean()),
    }


def main() -> None:
    df = load_data()
    print(f"标的: 513310 中韩半导体ETF | 区间: {df.index.min().date()} ~ {df.index.max().date()} | 共 {len(df)} 个交易日")
    print(f"参数: M={M}, N={N}（TYP=(O+C)/2）")
    print("=" * 66)

    df = compute_tpd(df)
    trades, in_position, signals = backtest(df)

    # 导出交易信号表（买入/卖出时刻）
    out_csv = PROJECT_ROOT / "data" / "bt_export" / f"tpd_signals_{M}_{N}.csv"
    signals.to_csv(out_csv, index=False)
    print(f"\n交易信号已导出 -> {out_csv}（{len(signals)} 条信号）")

    print(f"\n触发交易 {len(trades)} 笔：\n")
    for i, (bd, bp, sd, sp) in enumerate(trades, 1):
        ret = sp / bp - 1
        print(f"  [{i:>3}] 买 {str(bd)[:10]} @{bp:.3f} -> 卖 {str(sd)[:10]} @{sp:.3f}   收益 {ret:+.1%}")

    print("\n" + "=" * 66)
    s = summarize(trades, df, in_position)
    for k, v in s.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}" if "收益" not in k and "回撤" not in k else f"  {k}: {v:.2%}")
        else:
            print(f"  {k}: {v}")
    print("=" * 66)


if __name__ == "__main__":
    main()
