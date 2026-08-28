# -*- coding: utf-8 -*-
"""TPD红柱放大 — 收益率与年化收益率计算（实验区）"""
from pathlib import Path
import numpy as np
import pandas as pd
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tpd_macd_bar_detail import backtest_day, M, N, VOL_THR

DATA_CSV = Path("/home/chinapost/users/jaycode/quant_factors/data/bt_export/513310_5min.csv")

def main():
    df = pd.read_csv(DATA_CSV, parse_dates=["时间"])
    df["date"] = df["时间"].dt.date
    per_day = []
    for date, day in df.groupby("date"):
        if len(day) >= N + 15:
            pnl, _ = backtest_day(day, M, N, VOL_THR)
            per_day.append({"date": date, "daily_pnl": pnl})
    pdf = pd.DataFrame(per_day)
    n_days = len(pdf)
    dailies = pdf["daily_pnl"].values

    # 单利累计
    simple_total = float(dailies.sum())
    # 复利(几何)累计
    geo_total = float(np.prod(1 + dailies) - 1)
    # 年化（A股交易日按 242 计）
    annual = float((1 + geo_total) ** (242 / n_days) - 1)
    daily_mean = float(dailies.mean())
    daily_std = float(dailies.std())
    sharpe_like = daily_mean / daily_std * np.sqrt(242) if daily_std > 0 else np.nan
    win_days = int((dailies > 0).sum())

    print(f"参数: M={M}, N={N}, vol_thr={VOL_THR}")
    print(f"样本交易日: {n_days}（{pdf['date'].min()} ~ {pdf['date'].max()}）")
    print("=" * 56)
    print(f"单利累计收益率 : {simple_total:.2%}")
    print(f"复利累计收益率 : {geo_total:.2%}")
    print(f"年化收益率    : {annual:.2%}")
    print(f"日均收益      : {daily_mean*100:.3f}%/日")
    print(f"日收益标准差  : {daily_std*100:.3f}%")
    print(f"夏普(年化,无风险0): {sharpe_like:.2f}")
    print(f"盈利天数占比  : {win_days}/{n_days} ({win_days/n_days:.1%})")

if __name__ == "__main__":
    main()
