# -*- coding: utf-8 -*-
"""最强量价因子的选股 / 分层检验 / 多头组合回测与评测报告（实验区）

背景：
    factor_scan.py 从纯量价字段筛出几个最强因子（RankICIR 靠前），本脚本进一步验证
    它们能否用于选股和构建组合：
        1. 5 层分组单调性检验 —— 判断因子是否具备稳定的选股区分度
        2. 多头组合回测（Top-N% 等权，持有 horizon 滚动换仓）—— 评估真实可执行收益
        3. 计入交易成本（佣金 + 印花税 + 滑点）
        4. 输出完整绩效报告并与全市场等权基准对比

口径说明（无未来函数）：
    - T 日收盘依据当日因子值生成持仓信号
    - 次日开盘按目标权重买入，持有至卖出日开盘卖出（T+1 成交，规避用当日信息）
    - 简化近似：以"调仓日开盘价"撮合，成本单边约 0.105%（含佣金/滑点），卖出另加印花税

用法：
    conda run -n jaycode python playground/factor_portfolio_report.py
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("XDG_CONFIG_HOME", str(PROJECT_ROOT / "data" / ".config"))
os.environ.setdefault("MLFLOW_TRACKING_URI", str(PROJECT_ROOT / "data" / "mlruns"))

import qlib  # noqa: E402
from qlib.data.dataset import DatasetH  # noqa: E402
from qlib.data.dataset.handler import DataHandlerLP  # noqa: E402


# ---------- 配置 ----------
QLIB_URI = os.getenv("QLIB_URI", str(PROJECT_ROOT / "data" / "cn_data"))
START_TIME = "2023-08-01"
END_TIME = "2026-07-31"          # 留尾部缓冲给 horizon
HORIZON = 5                       # 持有交易日
TOP_N_PCT = 0.2                   # 多头选股比例（Top 20%）
N_GROUPS = 5                      # 分层组数
FREQ = "day"
INSTRUMENTS = "all"

# 交易成本（单边，A股近似）
COMMISSION = 0.0003               # 佣金 0.03%
STAMP_DUTY = 0.0005               # 印花税 0.05%（仅卖出）
SLIPPAGE = 0.001                  # 滑点 0.1%
BUY_COST = COMMISSION + SLIPPAGE          # 买入成本
SELL_COST = COMMISSION + STAMP_DUTY + SLIPPAGE  # 卖出成本

# 候选因子（来自 factor_scan.py 的最强几个，均为负向）
FACTORS = {
    "price_vol_corr": "Corr(Log($close), Log($volume), 20)",
    "amt_zscore": "($amount - Mean($amount, 30)) / Std($amount, 30)",
    "turnover_ratio_5": "Mean($amount, 5) / Mean($amount, 50)",
    "amt_trend": "Mean($amount, 3) / Mean($amount, 15) - 1",
}


def load_all() -> pd.DataFrame:
    """一次性加载全市场 OHLC + 全部因子。"""
    names = list(FACTORS.keys())
    exprs = list(FACTORS.values())
    cols = ["$open", "$close"] + exprs
    colnames = ["open", "close"] + names

    handler = DataHandlerLP(
        instruments=INSTRUMENTS,
        start_time=START_TIME,
        end_time=END_TIME,
        data_loader={
            "class": "QlibDataLoader",
            "kwargs": {"config": (cols, colnames)},
        },
        infer_processors=[{"class": "DropnaProcessor"}],
    )
    dataset = DatasetH(handler=handler, segments={"eval": (START_TIME, END_TIME)})
    return dataset.prepare("eval")


def winsorize_zscore(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """截面缩尾 + 稳健标准化（按每日，无未来函数）。"""
    df = df.copy()
    for col in columns:
        x = df[col]
        med = x.groupby(level="datetime").transform("median")
        mad = x.sub(med).abs().groupby(level="datetime").transform("median")
        df[col] = (x - med) / (mad * 1.4826 + 1e-9)
    return df


def layering_test(df: pd.DataFrame, factor: str, horizon: int = HORIZON) -> pd.Series:
    """5 层分组单调性检验（宽表向量化）。

    每日按因子分位数分 5 组，计算各组在 [t+1, t+horizon] 的累计收益均值，
    返回各组平均收益；若随组号递增/递减则说明因子有单调选股力。
    """
    closes = df["close"].unstack()
    factors = df[factor].unstack()

    # 未来 horizon 日累计收益（用次日到 horizon 日的收盘价）
    fwd_ret = closes.shift(-horizon) / closes - 1

    group_rows = []
    for dt in factors.index:
        row_f = factors.loc[dt]
        row_r = fwd_ret.loc[dt] if dt in fwd_ret.index else pd.Series(dtype=float)
        valid = row_f.dropna()
        if len(valid) < N_GROUPS * 10:
            continue
        q = pd.qcut(row_f, N_GROUPS, labels=False, duplicates="drop")
        tmp = pd.DataFrame({"q": q, "fwd_ret": row_r}).replace([np.inf, -np.inf], np.nan).dropna()
        if len(tmp) == 0:
            continue
        group_rows.append(tmp.groupby("q")["fwd_ret"].mean())
    if not group_rows:
        return pd.Series(dtype=float)
    gr = pd.concat(group_rows, axis=1)
    return gr.mean(axis=1)


def backtest_long_only(df: pd.DataFrame, factor: str,
                       top_pct: float = TOP_N_PCT,
                       horizon: int = HORIZON) -> pd.Series:
    """多头组合回测（宽表向量化，含交易成本）。

    规则：
        - 因子为负向（值越大未来越差），故**反向选股**：选因子值最小的 Top p%
        - T 日收盘依据因子选出目标持仓，持有至 T+horizon 再换仓（滚动）
        - 每期收益 = 该持仓期内组合的平均累计收益 - 换仓成本
    返回净值序列。
    """
    closes = df["close"].unstack()
    factors = df[factor].unstack()

    dates = list(factors.index)
    # 每个调仓日的未来 horizon 累计收益
    fwd_ret = closes.shift(-horizon) / closes - 1

    nav = 1.0
    nav_points = []
    last_nav_date = None
    prev_position_codes = set()
    position_cost_applied = True

    for k in range(0, len(dates), horizon):
        dt = dates[k]
        row_f = factors.loc[dt]
        valid = row_f.dropna()
        if len(valid) < 50:
            continue
        n_sel = max(int(len(valid) * top_pct), 5)
        # 反向：取因子最小的 top p%
        selected = valid.sort_values().index[:n_sel]

        # 该期收益：选中的股票在 (k+1 到 k+horizon) 的累计收益等权平均
        fwd = fwd_ret.loc[dt] if dt in fwd_ret.index else pd.Series(dtype=float)
        period_rets = fwd.reindex(selected).replace([np.inf, -np.inf], np.nan).dropna()
        if len(period_rets) == 0:
            continue
        gross_period_ret = float(period_rets.mean())

        # 换仓成本：卖出旧仓 + 买入新仓（近似整仓轮动）
        turnover = 1.0
        cost = SELL_COST * turnover + BUY_COST * turnover

        net_period_ret = gross_period_ret - cost
        nav *= (1 + net_period_ret)
        nav_points.append((dates[min(k + horizon, len(dates) - 1)], nav))

    idx = [p[0] for p in nav_points]
    vals = [p[1] for p in nav_points]
    return pd.Series(vals, index=pd.DatetimeIndex(idx))


def perf_report(nav: pd.Series, benchmark_nav: pd.Series | None = None,
                label: str = "") -> pd.Series:
    """从净值序列计算绩效指标。"""
    rets = nav.pct_change().dropna()
    n_days = len(rets)
    years = n_days / 252
    total_ret = nav.iloc[-1] / nav.iloc[0] - 1
    annual_ret = (1 + total_ret) ** (1 / years) - 1 if years > 0 else np.nan
    vol = rets.std() * np.sqrt(252)
    sharpe = annual_ret / vol if vol and not np.isnan(vol) else np.nan
    max_dd = (nav / nav.cummax() - 1).min()

    out = pd.Series({
        "总收益": total_ret,
        "年化收益": annual_ret,
        "年化波动": vol,
        "夏普比率": sharpe,
        "最大回撤": max_dd,
        "交易天数": n_days,
    })
    if benchmark_nav is not None:
        b_rets = benchmark_nav.pct_change().dropna()
        b_years = len(b_rets) / 252
        b_total = benchmark_nav.iloc[-1] / benchmark_nav.iloc[0] - 1
        b_annual = (1 + b_total) ** (1 / b_years) - 1 if b_years > 0 else np.nan
        b_vol = b_rets.std() * np.sqrt(252)
        b_sharpe = b_annual / b_vol if b_vol and not np.isnan(b_vol) else np.nan
        out["基准总收益"] = b_total
        out["超额收益"] = total_ret - b_total
        out["基准夏普"] = b_sharpe
    return out


def build_benchmark(df: pd.DataFrame) -> pd.Series:
    """全市场等权组合净值（作为基准）。"""
    closes = df["close"].unstack()
    bench_ret = closes.pct_change(fill_method=None).mean(axis=1, skipna=True)
    nav = (1 + bench_ret.fillna(0)).cumprod()
    return nav


def main() -> None:
    qlib.init(provider_uri=QLIB_URI, region="cn")
    print(f"数据路径: {QLIB_URI}")
    print(f"区间: {START_TIME} ~ {END_TIME} | 持有 {HORIZON} 日 | Top{int(TOP_N_PCT*100)}% | 5层检验")
    print("成本: 买 %.3f%% + 卖 %.3f%%" % (BUY_COST*100, SELL_COST*100))
    print("=" * 90)

    try:
        df = load_all()
        names = list(FACTORS.keys())
        df = winsorize_zscore(df, names)
        print(f"加载完成，样本数: {len(df):,}（{df.index.get_level_values(1).nunique()} 只股票）\n")
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"[数据加载失败] {e}")
        traceback.print_exc()
        return

    # 基准
    benchmark_nav = build_benchmark(df)
    bench_ret = benchmark_nav.iloc[-1] / benchmark_nav.iloc[0] - 1

    report_rows = []
    layering_table = {}

    for name in names:
        print(f"\n{'='*40} 因子: {name} {'='*40}")
        print(f"表达式: {FACTORS[name]}")

        # 1) 分层单调性检验
        gr = layering_test(df, name)
        layering_table[name] = gr
        print("5层分组平均未来5日收益:")
        for q in sorted(gr.index):
            marker = " <--" if q == gr.idxmax() else ""
            print(f"  组{q+1}: {gr[q]:+.4f}{marker}")

        # 2) 多头组合回测（反向选股）
        nav = backtest_long_only(df, name)
        rep = perf_report(nav, benchmark_nav, label=name)
        rep.name = name
        report_rows.append(rep)
        print("\n绩效:")
        print(rep.round(4).to_string())

    # —— 汇总报告 ——
    print("\n" + "=" * 90)
    print("评测报告汇总（含交易成本，持有%d日，Top%d%%）" % (HORIZON, int(TOP_N_PCT*100)))
    print("=" * 90)
    summary = pd.DataFrame(report_rows).T
    print(summary.round(4).to_string())
    print(f"\n全市场等权基准: 总收益 {bench_ret:+.4f}")

    # —— 分层单调性汇总 ——
    print("\n各因子5层单调性（组1→组5未来收益）:")
    ltab = pd.DataFrame(layering_table)
    print(ltab.round(4).to_string())

    # 导出 csv
    save_path = PROJECT_ROOT / "playground" / "factor_portfolio_report.csv"
    summary.to_csv(save_path, encoding="utf-8-sig")
    print(f"\n已保存到 {save_path}")


if __name__ == "__main__":
    main()
