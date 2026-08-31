# -*- coding: utf-8 -*-
"""TPD「上穿/下穿」日内 T+0 策略（research 中间区）

从 playground 的三个 tpd_intraday*.py 脚本合并而来：
    1. tpd_intraday_513310.py — 单标的纯日内回测（M=12,N=24 固定）
    2. tpd_intraday_oos.py     — 前段选参 / 后段样本外验证
    3. tpd_intraday_scan.py    — 全样本参数扫描 + 量比开仓过滤

思路：把日线 TPD 趋势择时适配到 5 分钟，约束为「纯日内、不过夜」。
    - TYP   := (open + close) / 2
    - TPD   := EMA(close, M) - EMA(TYP, M)
    - MATPD := MA(TPD, N)
    买入 = TPD 上穿 MATPD；卖出 = TPD 下穿 MATPD；收盘强制平仓。

用法示例：
    conda run -n jaycode python research/strategies/tpd_cross.py scan
    conda run -n jaycode python research/strategies/tpd_cross.py oos
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

DATA_CSV = PROJECT_ROOT / "data" / "bt_export" / "513310_5min.csv"
OUT_DIR = PROJECT_ROOT / "data" / "bt_export"


def load_data(data_csv: Path | str | None = None) -> pd.DataFrame:
    """读取 5分钟K线 CSV，补齐 date 列。"""
    path = Path(data_csv or DATA_CSV)
    df = pd.read_csv(path, parse_dates=["时间"])
    df["date"] = df["时间"].dt.date
    return df


def backtest_day(day_df: pd.DataFrame, m: int, n: int, vol_thr: float | None):
    """单日纯日内回测（TPD 上穿买 / 下穿卖），返回该日累计收益率。

    参数：
        day_df:  单交易日 5分钟K线。
        m:       TPD 的 EMA 周期。
        n:       MATPD 的 MA 周期。
        vol_thr: 量比开仓过滤阈值；None 表示不过滤。
    """
    typ = (day_df["开盘"] + day_df["收盘"]) / 2
    close = day_df["收盘"]
    tpd = close.ewm(span=m, adjust=False).mean() - typ.ewm(span=m, adjust=False).mean()
    matpd = tpd.rolling(n).mean()

    if vol_thr is not None:
        vol_base = day_df["成交量"].astype(float).rolling(10).mean()
        vol_ratio = day_df["成交量"].astype(float) / vol_base.replace(0, np.nan)

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
        if not position and i > 0 and i - 1 < len(buy_sig) and buy_sig.iloc[i - 1]:
            position = True
            entry_price = opens[i]
        elif position:
            force_close = (i == n_bar - 1) or sell_sig.iloc[i - 1]
            if force_close:
                pnl += closes[i] / entry_price - 1
                position = False
    return pnl


def evaluate(df: pd.DataFrame, m: int, n: int, vol_thr: float | None) -> dict:
    """在样本上评估一组参数，返回统计字典。"""
    pnls = []
    n_days = 0
    for _, day in df.groupby("date"):
        if len(day) < n + 15:  # 需要足够 bar 预热滚动均线/量基准
            continue
        n_days += 1
        pnls.append(backtest_day(day, m, n, vol_thr))
    pnls = np.array(pnls)
    total = float(pnls.sum())
    win_rate = float((pnls > 0).mean()) if len(pnls) else np.nan
    avg_win = float(pnls[pnls > 0].mean()) if (pnls > 0).any() else np.nan
    avg_loss = float(pnls[pnls <= 0].mean()) if (pnls <= 0).any() else np.nan
    return {
        "M": m, "N": n,
        "vol_thr": vol_thr if vol_thr is not None else "-",
        "days": n_days, "total": total,
        "daily": total / n_days if n_days else np.nan,
        "win_rate": win_rate, "avg_win": avg_win, "avg_loss": avg_loss,
    }


def _grids():
    return [6, 8, 12, 16], [12, 24, 36], [None, 1.2, 1.5]


# ---------- 链 1：全样本参数扫描 ----------
def run_scan(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """全样本参数网格扫描，按日均收益排序输出并落盘。"""
    df = df if df is not None else load_data()
    Ms, Ns, vol_thrs = _grids()

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
    print(result.head(20)[["M", "N", "vol_thr", "days", "total", "daily", "win_rate", "avg_win", "avg_loss"]]
          .round(4).to_string(index=False))

    print("\n" + "=" * 60)
    print(f"最优参数: M={best['M']}, N={best['N']}, vol_thr={best['vol_thr']}")
    print(f"  累计收益: {best['total']:.2%} | 日均: {best['daily']*100:.3f}%/日 | 胜率: {best['win_rate']:.1%}")

    out_csv = OUT_DIR / "tpd_intraday_scan.csv"
    result.to_csv(out_csv, index=False)
    print(f"\n完整扫描表已存 -> {out_csv}")
    return result


# ---------- 链 2：前段选参 + 样本外验证 ----------
def run_oos(df: pd.DataFrame | None = None, split: int = 20) -> dict:
    """仅在前段(in-sample)选参，再用后段(out-of-sample)独立验证，防过拟合。"""
    df = df if df is not None else load_data()
    dates = sorted(df["date"].unique())
    train_dates = set(dates[:split])
    test_dates = set(dates[split:])
    train = df[df["date"].isin(train_dates)]
    test = df[df["date"].isin(test_dates)]
    print(f"前段(in-sample): {len(train_dates)}天 ({dates[0]}~{dates[split-1]})")
    print(f"后段(out-of-sample): {len(test_dates)}天 ({dates[split]}~{dates[-1]})\n")

    Ms, Ns, vol_thrs = _grids()
    best = None
    for thr in vol_thrs:
        for m in Ms:
            for n in Ns:
                r = evaluate(train, m, n, thr)
                if best is None or (r["daily"] > best["daily"] and not np.isnan(r["daily"])):
                    best = {"M": m, "N": n, "vol_thr": thr, **r}

    print("前段最优参数:", f"M={best['M']}, N={best['N']}, vol_thr={best['vol_thr']}")
    print(f"  前段表现: 累计 {best['total']:.2%} | 日均 {best['daily']*100:.3f}%/日 | 胜率 {best['win_rate']:.1%}\n")

    oos = evaluate(test, best["M"], best["N"], best["vol_thr"])
    print("=" * 60)
    print("样本外(out-of-sample)验证结果")
    print("=" * 60)
    print(f"  参数沿用前段最优 M={best['M']}, N={best['N']}, vol_thr={best['vol_thr']}")
    print(f"  样本外天数: {oos['days']}")
    print(f"  累计收益: {oos['total']:.2%}")
    print(f"  日均收益: {oos['daily']*100:.3f}%/日")
    print(f"  胜率: {oos['win_rate']:.1%}")

    print("\n样本外逐日:")
    for _, day in test.groupby("date"):
        pnl = backtest_day(day, best["M"], best["N"], best["vol_thr"])
        if len(day) >= best["N"] + 15:
            print(f"  {day['date'].iloc[0]}  {pnl:+.4f}  ({pnl*100:+.3f}%)")
    return {"best": best, "oos": oos}


COMMANDS = {
    "scan": ("全样本参数扫描", run_scan),
    "oos": ("前段选参+样本外验证", run_oos),
}


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "scan"
    if cmd not in COMMANDS:
        print(f"用法: python tpd_cross.py [{'|'.join(COMMANDS)}]")
        return
    name, fn = COMMANDS[cmd]
    print(f"\n===== TPD 上穿/下穿 日内 — {name} =====\n")
    fn()


if __name__ == "__main__":
    main()
