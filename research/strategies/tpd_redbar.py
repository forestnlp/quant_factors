# -*- coding: utf-8 -*-
"""TPD「红柱放大」趋势加速日内 T+0 策略（research 中间区）

从 playground 的 tpd_macd_bar*.py 四个脚本合并而来：
    1. tpd_macd_bar.py       — 参数扫描 + 前段选参 / 后段样本外验证
    2. tpd_macd_bar_cost.py  — 交易成本敏感性分析（盈亏平衡费率）
    3. tpd_macd_bar_detail.py— 单日回测与逐笔交易明细
    4. tpd_macd_bar_perf.py  — 收益率 / 年化 / 夏普统计

思路：把 TPD 改造成类似 MACD 红柱放大的「趋势加速确认」信号。
    - TPD = EMA(close, M) - EMA((open+close)/2, M)
    - MATPD = MA(TPD, N)
    - BAR = TPD - MATPD  ~ MACD 柱
    - 买入：BAR > 0 且 BAR 较上一根递增（红柱放大）+ 量比过滤(可选)
    - 卖出：BAR 转 < 0（红翻绿）或收盘强制平仓（纯日内不过夜）

用法示例：
    conda run -n jaycode python research/strategies/tpd_redbar.py scan
    conda run -n jaycode python research/strategies/tpd_redbar.py cost
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# ---------- 配置 ----------
DATA_CSV = PROJECT_ROOT / "data" / "bt_export" / "513310_5min.csv"
OUT_DIR = PROJECT_ROOT / "data" / "bt_export"

DEFAULT_M = 6
DEFAULT_N = 12
DEFAULT_VOL_THR = 1.2


def backtest_day(day: pd.DataFrame, m: int, n: int, vol_thr) -> tuple[float, list[dict]]:
    """单日 TPD 红柱放大回测，返回 (该日收益率, 交易列表)。

    参数：
        day:     单交易日 5分钟K线（列：时间/开盘/收盘/最高/最低/成交量/成交额）。
        m:       TPD 的 EMA 周期。
        n:       MATPD 的 MA 周期。
        vol_thr: 量比过滤阈值；None 表示不过滤。
    返回：
        (当日累计收益, [{date,buy_time,buy_price,sell_time,sell_price,ret}, ...])
    """
    typ = (day["开盘"] + day["收盘"]) / 2
    close = day["收盘"]

    tpd = close.ewm(span=m, adjust=False).mean() - typ.ewm(span=m, adjust=False).mean()
    matpd = tpd.rolling(n).mean()
    bar = tpd - matpd                    # 类比 MACD 柱
    expanding = bar > bar.shift(1)       # 红柱放大（较上一根递增）

    vol_base = day["成交量"].astype(float).rolling(10).mean()
    vol_ratio = day["成交量"].astype(float) / vol_base.replace(0, np.nan)

    opens = day["开盘"].values
    closes = day["收盘"].values
    times = day["时间"].dt.strftime("%H:%M").values if "时间" in day else None
    dates = day["date"].astype(str).values
    bars = bar.values
    expand = expanding.values
    vr_arr = vol_ratio.values

    trades: list[dict] = []
    pnl = 0.0
    position = False
    entry_price = 0.0
    entry_time = None
    entry_date = None
    n_bar = len(day)

    for i in range(n_bar):
        long_ok = bool(bars[i] > 0 and expand[i])
        vr = vr_arr[i]
        long_ok = long_ok and (vr == vr and vr > vol_thr) if vol_thr is not None else long_ok

        if not position and i > 0 and long_ok:
            position = True
            entry_price = opens[i]
            entry_date = dates[i]
            entry_time = times[i] if times is not None else ""
        elif position:
            force_close = (i == n_bar - 1) or (bars[i] < 0)
            if force_close:
                ret = closes[i] / entry_price - 1
                pnl += ret
                trades.append({
                    "date": entry_date, "buy_time": entry_time, "buy_price": entry_price,
                    "sell_time": times[i] if times is not None else "",
                    "sell_price": closes[i], "ret": ret,
                })
                position = False
    return pnl, trades


def load_data(data_csv: Path | str | None = None) -> pd.DataFrame:
    """读取 5分钟K线 CSV，补齐 date 列。"""
    path = Path(data_csv or DATA_CSV)
    df = pd.read_csv(path, parse_dates=["时间"])
    df["date"] = df["时间"].dt.date
    return df


# ---------- 链 1：参数扫描 + 样本外验证 ----------
def evaluate(sub_df: pd.DataFrame, m: int, n: int, vol_thr) -> dict:
    """对子集逐日回测，汇总统计量。"""
    pnls = []
    for _, day in sub_df.groupby("date"):
        if len(day) >= n + 15:
            pnl, _ = backtest_day(day, m, n, vol_thr)
            pnls.append(pnl)
    pnls = np.array(pnls)
    total = float(pnls.sum())
    daily = total / len(pnls) if len(pnls) else np.nan
    win_rate = float((pnls > 0).mean()) if len(pnls) else np.nan
    return {"total": total, "daily": daily, "days": len(pnls), "win_rate": win_rate}


def run_scan(df: pd.DataFrame | None = None, split: int = 20) -> pd.DataFrame:
    """前段选参 / 后段样本外验证，返回完整扫描表。"""
    df = df if df is not None else load_data()
    dates = sorted(df["date"].unique())
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

    out_csv = OUT_DIR / "tpd_macd_bar_oos.csv"
    result.to_csv(out_csv, index=False)
    print(f"\n完整扫描表已存 -> {out_csv}")
    return result


# ---------- 链 2：成本敏感性 ----------
def get_signals(df: pd.DataFrame, m: int = DEFAULT_M, n: int = DEFAULT_N,
                vol_thr: float = DEFAULT_VOL_THR) -> list[tuple[float, float]]:
    """返回全部 (buy_price, sell_price) 交易对。"""
    all_trades: list[tuple[float, float]] = []
    for _, day in df.groupby("date"):
        if len(day) < n + 15:
            continue
        pnl, trades = backtest_day(day, m, n, vol_thr)
        for t in trades:
            all_trades.append((t["buy_price"], t["sell_price"]))
    return all_trades


def run_cost(df: pd.DataFrame | None = None) -> dict:
    """分档成本敏感性分析，输出各档累计/复利/年化与盈亏平衡费率。"""
    df = df if df is not None else load_data()
    trades = get_signals(df)
    n_days = df["date"].nunique()

    cost_levels = {
        "零成本(理想)": 0.0000,
        "低(万5/边)": 0.0005,
        "中(万10/边)": 0.0010,
        "高(万15/边)": 0.0015,
    }

    print(f"参数 M={DEFAULT_M}, N={DEFAULT_N}, vol_thr={DEFAULT_VOL_THR} | {n_days}交易日 | {len(trades)}笔交易\n")
    print(f"{'成本档':<16}{'单边费':>8}{'累计收益':>12}{'复利累计':>12}{'年化':>12}")
    print("-" * 62)

    results = {}
    for name, fee in cost_levels.items():
        rets = [sell / buy - 1 - 2 * fee for buy, sell in trades]
        simple = sum(rets)
        geo = np.prod([1 + r for r in rets]) - 1
        annual = (1 + geo) ** (242 / n_days) - 1
        results[name] = (simple, geo, annual)
        print(f"{name:<16}{fee*10000:>7.1f}‰{simple:>11.2%}{geo:>11.2%}{annual:>11.2%}")

    total_gross = sum(sell / buy - 1 for buy, sell in trades)
    breakeven = total_gross / len(trades) / 2 if trades else 0
    print("\n" + "=" * 46)
    print(f"毛利合计: {total_gross:.2%}, 共{len(trades)}笔")
    print(f"盈亏平衡单边费率(约): {breakeven*10000:.1f}‰/边")
    return {"results": results, "breakeven": breakeven, "n_trades": len(trades)}


# ---------- 链 3：交易明细 + 绩效统计 ----------
def run_detail(df: pd.DataFrame | None = None, m: int = DEFAULT_M,
               n: int = DEFAULT_N, vol_thr: float = DEFAULT_VOL_THR) -> tuple[pd.DataFrame, pd.DataFrame]:
    """输出逐笔明细与每日汇总，导出信号CSV。返回 (trades_df, per_day_df)。"""
    df = df if df is not None else load_data()

    all_trades: list[dict] = []
    per_day = []
    for date, day in df.groupby("date"):
        if len(day) >= n + 15:
            pnl, trades = backtest_day(day, m, n, vol_thr)
            per_day.append({"date": date, "n_trades": len(trades), "daily_pnl": pnl})
            all_trades += trades

    print(f"标的: 513310 | 参数 M={m}, N={n}, vol_thr={vol_thr}")
    print("=" * 70)

    trades_df = pd.DataFrame(all_trades)
    per_day_df = pd.DataFrame(per_day)
    print(f"\n总交易笔数: {len(trades_df)}")
    if len(trades_df):
        print("\n近 20 笔交易明细（按时间倒序）：")
        print(trades_df.tail(20)[["date", "buy_time", "buy_price", "sell_time", "sell_price", "ret"]]
              .round(4).to_string(index=False))

    total = float(per_day_df["daily_pnl"].sum())
    win_days = (per_day_df["daily_pnl"] > 0).sum()
    print("\n" + "=" * 60)
    print(f"累计收益(单利): {total:.2%}")
    print(f"盈利天数: {win_days}/{len(per_day_df)} ({win_days/len(per_day_df):.1%})")

    out_csv = OUT_DIR / "tpd_macd_bar_trades.csv"
    if len(trades_df):
        trades_df.to_csv(out_csv, index=False)
        print(f"\n交易明细已存 -> {out_csv}")
    return trades_df, per_day_df


def run_perf(df: pd.DataFrame | None = None, m: int = DEFAULT_M,
             n: int = DEFAULT_N, vol_thr: float = DEFAULT_VOL_THR) -> dict:
    """收益率与年化统计。"""
    df = df if df is not None else load_data()

    _, per_day_df = run_detail(df, m, n, vol_thr)
    n_days = len(per_day_df)
    dailies = per_day_df["daily_pnl"].values

    simple_total = float(dailies.sum())
    geo_total = float(np.prod(1 + dailies) - 1)
    annual = float((1 + geo_total) ** (242 / n_days) - 1) if n_days else np.nan
    daily_mean = float(dailies.mean()) if n_days else np.nan
    daily_std = float(dailies.std()) if n_days else np.nan
    sharpe_like = daily_mean / daily_std * np.sqrt(242) if (n_days and daily_std > 0) else np.nan
    win_days = int((dailies > 0).sum())

    print(f"参数: M={m}, N={n}, vol_thr={vol_thr}")
    print(f"样本交易日: {n_days}（{per_day_df['date'].min()} ~ {per_day_df['date'].max() if n_days else ''}）")
    print("=" * 56)
    print(f"单利累计收益率 : {simple_total:.2%}")
    print(f"复利累计收益率 : {geo_total:.2%}")
    print(f"年化收益率    : {annual:.2%}")
    print(f"日均收益      : {daily_mean*100:.3f}%/日")
    print(f"日收益标准差  : {daily_std*100:.3f}%")
    print(f"夏普(年化,无风险0): {sharpe_like:.2f}")
    print(f"盈利天数占比  : {win_days}/{n_days} ({win_days/n_days:.1%})")
    return {"simple": simple_total, "geo": geo_total, "annual": annual,
            "sharpe": sharpe_like, "win_days": win_days, "n_days": n_days}


COMMANDS = {
    "scan": ("参数扫描+样本外", run_scan),
    "cost": ("成本敏感性", run_cost),
    "detail": ("交易明细", run_detail),
    "perf": ("绩效统计", run_perf),
}


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "perf"
    if cmd not in COMMANDS:
        print(f"用法: python tpd_redbar.py [{'|'.join(COMMANDS)}]")
        return
    name, fn = COMMANDS[cmd]
    print(f"\n===== TPD 红柱放大 — {name} =====\n")
    fn()


if __name__ == "__main__":
    main()
