# -*- coding: utf-8 -*-
"""因子 IC/IR 评估 pipeline（实验区）

功能：
    1. 加载 Qlib 本地数据（全市场）
    2. 计算若干内置量价因子（Qlib 表达式）
    3. 计算未来 5 日收益作为 label
    4. 逐日计算 IC / RankIC，并汇总 IC 均值、ICIR、RankIC 均值、RankICIR
    5. 输出评估结果表格

用法：
    conda run -n qlib_rdagent python playground/factor_ic_ir_pipeline.py

成功标准：
    脚本无异常退出，打印每个因子的 IC / ICIR / RankIC / RankICIR 汇总表。
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd

import qlib
from qlib.data import D
from qlib.data.dataset import DatasetH
from qlib.data.dataset.handler import DataHandlerLP
from qlib.contrib.eva.alpha import calc_ic

# ---------- 配置 ----------
QLIB_URI = os.getenv("QLIB_URI", "C:/Users/jay/qlib_data/cn_data")
START_TIME = "2023-08-01"   # 近 3 年
END_TIME = "2026-08-13"
HORIZON = 5                 # 未来 5 日收益
FREQ = "day"

# 股票池：全市场（all.txt）
INSTRUMENTS = "all"

# 内置示例因子（Qlib 表达式）
FACTORS = {
    "momentum_20": "Ref($close, 0) / Ref($close, 20) - 1",          # 20 日动量
    "reversal_5": "Ref($close, 0) / Ref($close, 5) - 1",            # 5 日反转
    "volatility_20": "Std($close, 20) / Mean($close, 20)",          # 20 日波动率
    "volume_ratio_5": "Mean($volume, 5) / Mean($volume, 20)",       # 量比
    "high_low_range": "($high - $low) / $close",                    # 日内振幅
}


def build_label(horizon: int = HORIZON) -> pd.Series:
    """构造未来 horizon 日收益作为 label（Qlib 表达式）。"""
    return f"Ref($close, -{horizon}) / Ref($close, 0) - 1"


def load_factor_data(factor_expr: str, label_expr: str) -> pd.DataFrame:
    """加载单个因子的数据（因子值 + label），返回 MultiIndex (datetime, instrument)。"""
    handler = DataHandlerLP(
        instruments=INSTRUMENTS,
        start_time=START_TIME,
        end_time=END_TIME,
        data_loader={
            "class": "QlibDataLoader",
            "kwargs": {"config": {"feature": [factor_expr], "label": [label_expr]}},
        },
        infer_processors=[
            {"class": "DropnaProcessor"},
        ],
        learn_processors=[],
    )
    dataset = DatasetH(handler=handler, segments={"train": (START_TIME, END_TIME)})
    df = dataset.prepare("train")
    return df


def evaluate_factor(name: str, factor_expr: str) -> pd.DataFrame:
    """计算单个因子的 IC / RankIC 序列，并汇总统计量。"""
    label_expr = build_label()
    df = load_factor_data(factor_expr, label_expr)

    # 因子值 / label 取第一列
    pred = df.iloc[:, 0]
    label = df.iloc[:, 1]

    ic, ric = calc_ic(pred, label, dropna=True)

    summary = {
        "factor": name,
        "IC_mean": ic.mean(),
        "IC_std": ic.std(),
        "ICIR": ic.mean() / ic.std() if ic.std() else np.nan,
        "RankIC_mean": ric.mean(),
        "RankIC_std": ric.std(),
        "RankICIR": ric.mean() / ric.std() if ric.std() else np.nan,
        "IC_positive_ratio": (ic > 0).mean(),
        "n_days": len(ic),
    }
    return pd.Series(summary)


def main() -> None:
    qlib.init(provider_uri=QLIB_URI, region="cn")

    print(f"股票池: {INSTRUMENTS} | 区间: {START_TIME} ~ {END_TIME} | 收益周期: {HORIZON} 日")
    print("=" * 80)

    results = []
    for name, expr in FACTORS.items():
        print(f"\n>>> 评估因子: {name}")
        print(f"    表达式: {expr}")
        try:
            row = evaluate_factor(name, expr)
            results.append(row)
            print(f"    IC={row['IC_mean']:.4f}  ICIR={row['ICIR']:.4f}  "
                  f"RankIC={row['RankIC_mean']:.4f}  RankICIR={row['RankICIR']:.4f}")
        except Exception as e:  # noqa: BLE001
            import traceback
            print(f"    [失败] {e}")
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("因子 IC/IR 评估汇总")
    print("=" * 80)
    if results:
        summary_df = pd.DataFrame(results).set_index("factor")
        print(summary_df.round(4).to_string())


if __name__ == "__main__":
    main()
