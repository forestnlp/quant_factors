# -*- coding: utf-8 -*-
"""两个 TPD 类因子的择时回测对比（实验区）

背景：
    用户提供两个"价格压力(TPD)"公式，均为短线摆动择时信号：
        cross(tpd, matpd)  -> 买入
        cross(matpd, tpd)  -> 卖出

    公式1：
        TYP  := (O+C+L+H)/4
        BOL  := MA(C,6); UB/LB := BOL±STD(C,6)   # 死代码，未使用
        TPD  := EMA(C,M) - EMA(TYP,M)
        MATPD:= MA(TPD,N)
        参数 M/N/X 未定义

    公式2：
        TYP  := (O+C)/2
        TPD  := EMA(C,7) - EMA(TYP,7)
        MATPD:= MA(TPD,6)

目的：
    在相同参数(M=7,N=6)、相同回测规则下，仅改变 TYP 定义，
    回答"哪种典型价定义的 TPD 更好"。

方法：
    - qlib 加载全市场 OHLC
    - 逐股向量化择时：TPD 上穿 MATPD 次日开盘买入，下穿次日开盘卖出
    - 统计每只股票的交易次数、胜率、累计收益、盈亏比、平均持仓天数
    - 汇总对比两因子（排除信号过少的股票）

用法：
    conda run -n jaycode python playground/compare_tpd_factors.py
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("XDG_CONFIG_HOME", str(PROJECT_ROOT / "data" / ".config"))
os.environ.setdefault("MLFLOW_TRACKING_URI", str(PROJECT_ROOT / "data" / "mlruns"))

import qlib  # noqa: E402
from qlib.data import D  # noqa: E402


# ---------- 配置 ----------
QLIB_URI = os.getenv("QLIB_URI", str(PROJECT_ROOT / "data" / "cn_data"))
START_TIME = "2023-08-01"
END_TIME = "2026-08-06"
FREQ = "day"

# 公平对比：两公式统一使用 M=7, N=6（公式2原参数），仅 TYP 定义不同
M = 7          # EMA 周期
N = 6          # MATPD 的 MA 周期
MIN_TRADES = 5  # 至少 5 次交易才纳入统计，避免信号过少失真

# 两套因子定义：返回 (tpd_expr, matpd_expr)
def build_factor_1():
    """TYP=(O+C+L+H)/4"""
    typ = r"(($open + $close + $high + $low) / 4)"
    tpd = f"EMA($close,{M}) - EMA({typ},{M})"
    matpd = f"Mean({tpd},{N})"
    return tpd, matpd


def build_factor_2():
    """TYP=(O+C)/2"""
    typ = r"(($open + $close) / 2)"
    tpd = f"EMA($close,{M}) - EMA({typ},{M})"
    matpd = f"Mean({tpd},{N})"
    return tpd, matpd


def load_all(factor_builder):
    """加载全市场数据：OHLC + tpd + matpd，返回 MultiIndex DataFrame。"""
    tpd, matpd = factor_builder()
    exprs = [
        "$open", "$close",
        tpd,
        matpd,
    ]
    names = ["open", "close", "tpd", "matpd"]
    # 先取股票池（按区间内实际有交易的股票），再一次性加载
    instruments = D.list_instruments(D.instruments("all"), start_time=START_TIME, end_time=END_TIME, as_list=True)
    df = D.features(instruments, exprs, start_time=START_TIME, end_time=END_TIME, freq=FREQ)
    df.columns = names
    # 去掉前 M+N 行（EMA/MA warmup），只保留全部非空的行
    df = df.dropna()
    return df


def backtest_stock(g: pd.DataFrame) -> dict | None:
    """单只股票的向量化择时回测。

    规则：
        - TPD 上穿 MATPD 当日收盘产生买入信号，次一交易日开盘价买入
        - TPD 下穿 MATPD 当日收盘产生卖出信号，次一交易日开盘价卖出
        - 用次日开盘成交，规避用当日未来信息（无未来函数）
    返回统计量；若交易次数过少返回 None。
    """
    g = g.sort_index()
    if len(g) < 10:
        return None

    prev_tpd = g["tpd"].shift(1)
    prev_matpd = g["matpd"].shift(1)
    buy_sig = (g["tpd"] > g["matpd"]) & (prev_tpd <= prev_matpd)   # 上穿
    sell_sig = (g["tpd"] < g["matpd"]) & (prev_tpd >= prev_matpd)  # 下穿

    open_ = g["open"].values
    close = g["close"].values
    n = len(g)

    trades = []          # 每笔：(买入价, 卖出价)
    position = False
    entry_price = 0.0
    entry_day = 0
    hold_days = []
    for i in range(n):
        # 用前一日信号 + 今日开盘成交
        if i > 0 and buy_sig.iloc[i - 1] and not position:
            position = True
            entry_price = open_[i]
            entry_day = i
        elif i > 0 and sell_sig.iloc[i - 1] and position:
            trades.append((entry_price, open_[i]))
            hold_days.append(i - entry_day)
            position = False

    # 回测结束仍持仓：按最后收盘平仓（虚拟）
    if position:
        trades.append((entry_price, close[-1]))
        hold_days.append(n - 1 - entry_day)

    if len(trades) < MIN_TRADES:
        return None

    rets = [sell / buy - 1 for buy, sell in trades]
    wins = [r for r in rets if r > 0]
    gross_profit = sum(r for r in rets if r > 0)
    gross_loss = abs(sum(r for r in rets if r <= 0))
    cum = np.prod([1 + r for r in rets]) - 1

    return {
        "n_trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "cum_return": cum,
        "avg_ret": np.mean(rets),
        "profit_loss_ratio": (gross_profit / len(wins)) / (gross_loss / max(len(trades) - len(wins), 1)) if wins and gross_loss > 0 else float("nan"),
        "avg_hold_days": np.mean(hold_days) if hold_days else float("nan"),
    }


def evaluate(df: pd.DataFrame) -> pd.DataFrame:
    """全市场逐股回测，汇总统计。"""
    records = []
    for _, g in df.groupby(level=0):
        r = backtest_stock(g)
        if r:
            records.append(r)
    if not records:
        return pd.DataFrame()
    res = pd.DataFrame(records)

    def wavg(x, w):
        return np.average(x, weights=w) if x.sum() > 0 else float("nan")

    summary = {
        "股票数": len(res),
        "总交易次数": int(res["n_trades"].sum()),
        "平均每股胜率": res["win_rate"].mean(),
        "加权胜率(按次数)": wavg(res["win_rate"], res["n_trades"]),
        "平均累计收益/股": res["cum_return"].mean(),
        "中位累计收益/股": res["cum_return"].median(),
        "盈利股票占比": (res["cum_return"] > 0).mean(),
        "平均盈亏比": np.nanmean(res["profit_loss_ratio"]),
        "平均持仓天数": np.nanmean(res["avg_hold_days"]),
    }
    return pd.Series(summary)


def main() -> None:
    qlib.init(provider_uri=QLIB_URI, region="cn")
    print(f"数据路径: {QLIB_URI}")
    print(f"区间: {START_TIME} ~ {END_TIME} | EMA周期 M={M}, MATPD均线 N={N} | MIN_TRADES={MIN_TRADES}")
    print("=" * 70)

    summaries = []
    for label, builder in [("公式1 TYP=(O+C+L+H)/4", build_factor_1),
                           ("公式2 TYP=(O+C)/2", build_factor_2)]:
        print(f"\n>>> 回测 [{label}] ...")
        df = load_all(builder)
        print(f"    加载样本: {len(df):,}（{df.index.get_level_values(0).nunique()} 只股票）")
        s = evaluate(df)
        s.name = label
        summaries.append(s)
        if len(s):
            print(s.round(4).to_string())
        else:
            print("    无有效交易样本")

    print("\n" + "=" * 70)
    print("两因子对比汇总")
    print("=" * 70)
    cmp = pd.concat(summaries, axis=1)
    print(cmp.round(4).to_string())


if __name__ == "__main__":
    main()
