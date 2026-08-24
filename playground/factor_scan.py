# -*- coding: utf-8 -*-
"""批量量价因子 IC 筛选（实验区）

基于 qlib cn_data 仅有的量价字段（open/high/low/close/vwap/volume/amount），
构造多类经典因子，用同一套 IC/IR 框架批量评估并排序，挑出有效的候选因子。

因子类别：
    1. 动量 / 反转      —— 不同周期的过去收益
    2. 波动率           —— 波动大小与未来收益
    3. 流动性 / 换手    —— volume/amount 相关
    4. 量价关系         —— 成交量与价格变化的背离/相关性
    5. 位置 / 形态       —— 收盘价在区间中的位置、上下影线

用法：
    conda run -n jaycode python playground/factor_scan.py
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
from qlib.contrib.eva.alpha import calc_ic  # noqa: E402


# ---------- 配置 ----------
QLIB_URI = os.getenv("QLIB_URI", str(PROJECT_ROOT / "data" / "cn_data"))
START_TIME = "2023-08-01"
END_TIME = "2026-08-06"
HORIZON = 5                 # 未来 5 日收益
FREQ = "day"
INSTRUMENTS = "all"

# ---------- 候选因子（量价，qlib 表达式）----------
FACTORS = {
    # === 动量 / 反转 ===
    "mom_10": "$close / Ref($close, 10) - 1",
    "mom_20": "$close / Ref($close, 20) - 1",
    "mom_60": "$close / Ref($close, 60) - 1",
    "rev_1": "Ref($close, 1) / $close - 1",           # 隔夜/日内反转（反向）
    "rev_5": "Ref($close, 5) / $close - 1",
    "mom_accel": "($close / Ref($close, 20) - 1) - ($close / Ref($close, 40) - 1)",  # 动量加速度

    # === 波动率 ===
    "vol_20": "Std($close, 20) / Mean($close, 20)",
    "vol_60": "Std($close, 60) / Mean($close, 60)",
    "vol_change": "(Std($close, 5) / Std($close, 25))",  # 短期波动/长期波动

    # === 流动性 / 换手（用 amount 替代，因无股本数据）===
    "amt_zscore": "($amount - Mean($amount, 30)) / Std($amount, 30)",   # 成交额异常放大
    "amt_trend": "Mean($amount, 3) / Mean($amount, 15) - 1",            # 近期成交额趋势
    "turnover_ratio_5": "Mean($amount, 5) / Mean($amount, 50)",         # 量能比

    # === 量价关系 ===
    "price_vol_corr": "Corr(Log($close), Log($volume), 20)",           # 量价相关性

    # === 位置 / 形态 ===
    "high_pos": "($close - Ref(Max($high, 60), 0)) / (Ref(Max($high, 120), 0) - Ref(Min($low, 250), 0))",  # 区间位置
    "body_position": "($close - $open) / ($high - $low + 1e-9)",             # K线实体相对振幅位置
    "upper_wick_approx": "($high - ($open + $close) / 2) / ($high - $low + 1e-9)",   # 上影近似
    "lower_wick_approx": "(($open + $close) / 2 - $low) / ($high - $low + 1e-9)",    # 下影近似

    # === RSI / 强弱（经典反转指标）===
    "bias_20": "($close - Mean($close, 30)) / Std($close, 10)",   # 乖离率类
}


def build_label(horizon: int = HORIZON) -> str:
    return f"Ref($close, -{horizon}) / $close - 1"


def load_factor_data(factor_exprs: list[str], factor_names: list[str]) -> pd.DataFrame:
    label_expr = build_label()
    handler = DataHandlerLP(
        instruments=INSTRUMENTS,
        start_time=START_TIME,
        end_time=END_TIME,
        data_loader={
            "class": "QlibDataLoader",
            "kwargs": {
                "config": (factor_exprs + [label_expr], factor_names + ["y_future"]),
            },
        },
        infer_processors=[
            {"class": "DropnaProcessor"},
        ],
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
        x_norm = (x - med) / (mad * 1.4826 + 1e-9)
        df[col] = x_norm.clip(-3, 3)
    return df


def main() -> None:
    qlib.init(provider_uri=QLIB_URI, region="cn")
    print(f"数据路径: {QLIB_URI}")
    print(f"区间: {START_TIME} ~ {END_TIME} | horizon={HORIZON} 日 | 候选因子数: {len(FACTORS)}")
    print("=" * 90)

    names = list(FACTORS.keys())
    exprs = [FACTORS[n] for n in names]

    try:
        df = load_factor_data(exprs, names)
        print(f"加载完成，样本数: {len(df):,}（{df.index.get_level_values(1).nunique()} 只股票）\n")
        df = winsorize_zscore(df, names)
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"[数据加载失败] {e}")
        traceback.print_exc()
        return

    label = df["y_future"]
    results = []
    failed = []
    for name in names:
        try:
            pred = df[name]
            ic, ric = calc_ic(pred, label, dropna=True)
            ic_mean = float(ic.mean()) if len(ic) else np.nan
            ic_std = float(ic.std()) if len(ic) else np.nan
            ric_mean = float(ric.mean()) if len(ric) else np.nan
            ric_std = float(ric.std()) if len(ric) else np.nan
            row = {
                "factor": name,
                "expr": FACTORS[name],
                "IC_mean": ic_mean,
                "ICIR": ic_mean / ic_std if (ic_std and not pd.isna(ic_std)) else np.nan,
                "RankIC_mean": ric_mean,
                "RankICIR": ric_mean / ric_std if (ric_std and not pd.isna(ric_std)) else np.nan,
                "IC_pos_ratio": float((ic > 0).mean()) if len(ic) else np.nan,
            }
            results.append(row)
        except Exception as e:  # noqa: BLE001
            failed.append((name, str(e)[:100]))

    res_df = pd.DataFrame(results)

    print("=" * 90)
    print(f"因子 IC 筛选结果（按 |RankICIR| 降序）")
    print("=" * 90)
    out = res_df.copy()
    out["abs_RankICIR"] = out["RankICIR"].abs()
    out = out.sort_values("abs_RankICIR", ascending=False)
    show = out[["factor", "IC_mean", "ICIR", "RankIC_mean", "RankICIR", "IC_pos_ratio"]].round(4)
    print(show.to_string(index=False))

    print("\n失败/无效表达式:")
    for n, err in failed:
        print(f"  {n}: {err}")

    # 导出 csv
    save_path = PROJECT_ROOT / "playground" / "factor_scan_result.csv"
    res_df.to_csv(save_path, index=False, encoding="utf-8-sig")
    print(f"\n已保存到 {save_path}")


if __name__ == "__main__":
    main()
