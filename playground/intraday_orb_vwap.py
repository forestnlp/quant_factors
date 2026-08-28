# -*- coding: utf-8 -*-
"""中韩半导体ETF(513310) 5分钟 — 换框架：ORB + VWAP 纯日内 T+0（实验区）

替代被证伪的 TPD 搬移，改用更适合日内的两类框架：

[1] ORB 开盘区间突破（动量）
    取开盘前 window 根 bar 的最高/最低价作为区间；
    价格向上突破区间上沿 -> 买入；向下跌破下沿 -> 卖出；
    收盘强制平仓。仅做单向（先突破哪个方向就朝哪边），不过夜。

[2] VWAP 均值回归
    计算当日累计 VWAP；当价格偏离 VWAP 超过 k*标准差时反向开仓，
    回归到 VWAP 附近或收盘平仓。

每个框架都做：参数扫描 + 前段20天选参 / 后段11天样本外验证。
数据来源：data/bt_export/513310_5min.csv
用法：
    conda run -n jaycode python playground/intraday_orb_vwap.py

成功标准：
    脚本无异常退出，分别输出两框架的前段最优与样本外表现。
"""

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_CSV = PROJECT_ROOT / "data" / "bt_export" / "513310_5min.csv"


# ---------- ORB 单日回测 ----------
def backtest_orb(day: pd.DataFrame, window: int) -> float:
    """ORB：开盘 window 根bar定区间，突破后单向持有至收盘。"""
    high = day["最高"].values
    low = day["最低"].values
    opens = day["开盘"].values
    closes = day["收盘"].values
    n = len(day)
    if n <= window + 2:
        return 0.0

    range_high = float(high[:window].max())
    range_low = float(low[:window].min())

    pnl = 0.0
    position = None       # 'long' / 'short'
    entry_price = 0.0
    for i in range(window, n):
        if position is None and i > window - 1:
            if closes[i] > range_high:
                position = "long"
                entry_price = opens[i]
            elif closes[i] < range_low:
                position = "short"
                entry_price = opens[i]
        elif position == "long":
            force_close = (i == n - 1) or (closes[i] < range_low)
            if force_close:
                pnl += closes[i] / entry_price - 1
                position = None
        elif position == "short":
            force_close = (i == n - 1) or (closes[i] > range_high)
            if force_close:
                pnl += 1 - closes[i] / entry_price
                position = None
    return pnl


# ---------- VWAP 单日回测 ----------
def backtest_vwap(day: pd.DataFrame, k: float) -> float:
    """VWAP 均值回归：偏离 k*std 反向开仓，回到中枢或收盘平仓。"""
    typ = (day["开盘"] + day["收盘"]) / 2
    vol = day["成交量"].astype(float)
    cum_tp = (typ * vol).cumsum()
    cum_v = vol.cumsum().replace(0, np.nan)
    vwap = cum_tp / cum_v

    # 当日价格相对 VWAP 的滚动标准差
    roll_std = (typ - vwap).rolling(12).std().fillna(method="bfill")

    opens = day["开盘"].values
    closes = day["收盘"].values
    vwap_arr = vwap.values
    std_arr = roll_std.values
    n = len(day)

    pnl = 0.0
    position = None       # 'long'(价低于vwap买) / 'short'
    entry_price = 0.0
    for i in range(n):
        dev = closes[i] - vwap_arr[i]
        band = k * std_arr[i] if std_arr[i] == std_arr[i] and std_arr[i] > 1e-9 else 0.0
        if position is None:
            if dev < -band:   # 显著低于VWAP，赌回归 -> 做多
                position = "long"
                entry_price = opens[i]
            elif dev > band:  # 显著高于VWAP，赌回落 -> 做空
                position = "short"
                entry_price = opens[i]
        elif position == "long":
            force_close = (i == n - 1) or (closes[i] >= vwap_arr[i])
            if force_close:
                pnl += closes[i] / entry_price - 1
                position = None
        elif position == "short":
            force_close = (i == n - 1) or (closes[i] <= vwap_arr[i])
            if force_close:
                pnl += 1 - closes[i] / entry_price
                position = None
    return pnl


def evaluate(sub_df: pd.DataFrame, framework: str, **params):
    """在子样本上评估一组参数，返回统计。"""
    pnls = []
    for _, day in sub_df.groupby("date"):
        if framework == "orb":
            pnls.append(backtest_orb(day, params["window"]))
        else:
            pnls.append(backtest_vwap(day, params["k"]))
    pnls = np.array(pnls)
    total = float(pnls.sum())
    daily = total / len(pnls) if len(pnls) else np.nan
    win_rate = float((pnls > 0).mean()) if len(pnls) else np.nan
    return {"total": total, "daily": daily, "days": len(pnls), "win_rate": win_rate}


def scan_and_oos(df: pd.DataFrame, name: str, framework: str, param_grid: list, split: int = 20):
    """统一流程：前段选参 -> 样本外验证。"""
    dates = sorted(df["date"].unique())
    train = df[df["date"].isin(set(dates[:split]))]
    test = df[df["date"].isin(set(dates[split:]))]

    print("\n" + "#" * 60)
    print(f"框架: {name}")
    print("#" * 60)

    # 前段选参
    best = None
    for p in param_grid:
        r = evaluate(train, framework, **p)
        if best is None or (r["daily"] > best["daily"] and not np.isnan(r["daily"])):
            best = {"params": p, **r}
    print(f"[前段最优] {best['params']} | 累计 {best['total']:.2%} | 日均 {best['daily']*100:.3f}%/日 | 胜率 {best['win_rate']:.1%}")

    # 样本外
    oos = evaluate(test, framework, **best["params"])
    print(f"[样本外]  沿用前段参数 {best['params']} | 累计 {oos['total']:.2%} | "
          f"日均 {oos['daily']*100:.3f}%/日 | 胜率 {oos['win_rate']:.1%}")
    return best, oos


def main() -> None:
    df = pd.read_csv(DATA_CSV, parse_dates=["时间"])
    df["date"] = df["时间"].dt.date
    print(f"标的: 513310 | {df['date'].nunique()} 交易日\n")

    orb_grid = [{"window": w} for w in [12, 18, 24]]           # 60/90/120分钟区间
    vwap_grid = [{"k": k} for k in [0.5, 1.0, 1.5, 2.0]]

    scan_and_oos(df, "ORB 开盘区间突破", "orb", orb_grid)
    scan_and_oos(df, "VWAP 均值回归", "vwap", vwap_grid)


if __name__ == "__main__":
    main()
