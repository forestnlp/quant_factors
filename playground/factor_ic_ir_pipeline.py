# -*- coding: utf-8 -*-
"""因子 IC/IR 评估 pipeline（实验区）

功能：
    1. 加载 Qlib 本地数据（全市场）
    2. 计算若干内置量价因子（Qlib 表达式）
    3. 计算未来 5 日收益作为 label
    4. 逐日计算 IC / RankIC，并汇总 IC 均值、ICIR、RankIC 均值、RankICIR
    5. 输出评估结果表格

改进点：
    - 一次加载全部因子（不再一因子一 Handler，减少 IO）
    - 增加截面缩尾 + 稳健标准化预处理（按每日截面，无未来函数）
    - 行情读取带 horizon 尾部缓冲，避免末尾标签缺失
    - 数据路径从 .env 的 QLIB_URI 读取，不硬编码

用法：
    conda run -n jaycode python playground/factor_ic_ir_pipeline.py

成功标准：
    脚本无异常退出，打印每个因子的 IC / ICIR / RankIC / RankICIR 汇总表。
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 将 mlflow 的配置与跟踪目录重定向到项目内（避免沙箱拦截 ~/.config/mlflow）。
# 必须在 import qlib / mlflow 之前设置才生效。
os.environ.setdefault("XDG_CONFIG_HOME", str(PROJECT_ROOT / "data" / ".config"))
os.environ.setdefault("MLFLOW_TRACKING_URI", str(PROJECT_ROOT / "data" / "mlruns"))

import qlib  # noqa: E402
from qlib.data.dataset import DatasetH  # noqa: E402
from qlib.data.dataset.handler import DataHandlerLP  # noqa: E402
from qlib.contrib.eva.alpha import calc_ic  # noqa: E402


# ---------- 配置 ----------
# 优先取环境变量 QLIB_URI，其次 .env，最后回退相对项目根的 data/cn_data
_env = {}
if (PROJECT_ROOT / ".env").exists():
    for line in (PROJECT_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        _env[key.strip()] = val.strip()

QLIB_URI = os.getenv("QLIB_URI", _env.get("QLIB_URI", str(PROJECT_ROOT / "data" / "cn_data")))

# 数据区间需落在已下载的 qlib 数据范围内（investment_data 日更，最新至 2026-08-13）
START_TIME = "2023-08-01"   # 近 3 年
END_TIME = "2026-08-06"     # 预留 horizon 尾部缓冲，避免末尾标签缺失
HORIZON = 5                 # 未来 5 日收益
FREQ = "day"

# 股票池：全市场（all.txt）
INSTRUMENTS = "all"

# 内置示例因子（Qlib 表达式）
FACTORS = {
    "momentum_20": "$close / Ref($close, 20) - 1",          # 20 日动量
    "reversal_5": "$close / Ref($close, 5) - 1",            # 5 日反转
    "volatility_20": "Std($close, 20) / Mean($close, 20)",  # 20 日波动率
    "volume_ratio_5": "Mean($volume, 5) / Mean($volume, 20)",  # 量比
    "high_low_range": "($high - $low) / $close",            # 日内振幅
    # —— TPD 类因子（用户公式，统一参数 EMA周期=7，与择时回测一致）——
    #watch 公式1: TYP=(O+C+L+H)/4；TPD=EMA(C,7)-EMA(TYP,7)
    "tpd_ohlc4": "EMA($close, 7) - EMA(($open + $close + $high + $low) / 4, 7)",
    # 公式2: TYP=(O+C)/2；TPD=EMA(C,7)-EMA(TYP,7)
    "tpd_oc2": "EMA($close, 7) - EMA(($open + $close) / 2, 7)",
}


def build_label(horizon: int = HORIZON) -> str:
    """构造未来 horizon 日收益作为 label（Qlib 表达式）。"""
    return f"Ref($close, -{horizon}) / $close - 1"


def load_factor_data(factor_exprs: list[str], factor_names: list[str]) -> pd.DataFrame:
    """一次性加载全部因子的数据（因子值 + label），返回 MultiIndex (datetime, instrument)。

    行情读取截止到 END_TIME；由于 label 是未来 horizon 日收益，
    末尾不足 horizon 天的样本会因 label 为 NaN 被 DropnaProcessor 丢弃。
    """
    label_expr = build_label()
    handler = DataHandlerLP(
        instruments=INSTRUMENTS,
        start_time=START_TIME,
        end_time=END_TIME,
        data_loader={
            "class": "QlibDataLoader",
            "kwargs": {
                # (exprs, names)：显式指定列名，返回单层索引 DataFrame
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
    """对指定列做截面缩尾 + 稳健标准化（Robust Z-Score）。

    按每日截面分别计算 median / MAD，天然不跨时间、无未来函数：
        1. 减去截面中位数
        2. 除以 MAD * 1.4826，并截断到 [-3, 3]（去极值/缩尾）
    返回处理后的副本。
    """
    df = df.copy()
    for col in columns:
        x = df[col]
        med = x.groupby(level="datetime").transform("median")
        mad = x.sub(med).abs().groupby(level="datetime").transform("median")
        x_norm = (x - med) / (mad * 1.4826 + 1e-9)
        df[col] = x_norm.clip(-3, 3)
    return df


def evaluate_factor(df: pd.DataFrame, name: str) -> pd.Series:
    """计算单个因子的 IC / RankIC 序列，并汇总统计量。"""
    pred = df[name]
    label = df["y_future"]

    ic, ric = calc_ic(pred, label, dropna=True)
    # calc_ic 返回逐日 IC 序列；若为空则统计量为 NaN
    ic_mean = float(ic.mean()) if len(ic) else np.nan
    ic_std = float(ic.std()) if len(ic) else np.nan
    ric_mean = float(ric.mean()) if len(ric) else np.nan
    ric_std = float(ric.std()) if len(ric) else np.nan

    summary = {
        "factor": name,
        "IC_mean": ic_mean,
        "IC_std": ic_std,
        "ICIR": ic_mean / ic_std if (ic_std and not pd.isna(ic_std)) else np.nan,
        "RankIC_mean": ric_mean,
        "RankIC_std": ric_std,
        "RankICIR": ric_mean / ric_std if (ric_std and not pd.isna(ric_std)) else np.nan,
        "IC_positive_ratio": float((ic > 0).mean()) if len(ic) else np.nan,
        "n_days": len(ic),
    }
    return pd.Series(summary)


def main() -> None:
    qlib.init(provider_uri=QLIB_URI, region="cn")

    print(f"数据路径: {QLIB_URI}")
    print(f"股票池: {INSTRUMENTS} | 评估区间: {START_TIME} ~ {END_TIME} | 收益周期: {HORIZON} 日")
    print("=" * 80)

    factor_names = list(FACTORS.keys())
    factor_exprs = [FACTORS[n] for n in factor_names]

    results = []
    try:
        df = load_factor_data(factor_exprs, factor_names)
        print(f"加载完成，样本数: {len(df)}（含 {df.index.get_level_values(1).nunique()} 只股票）\n")

        # 截面缩尾 + 稳健标准化（去极值），再进入 IC 评估
        df = winsorize_zscore(df, factor_names)
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"[数据加载失败] {e}")
        traceback.print_exc()
        return

    for name in factor_names:
        print(f">>> 评估因子: {name}")
        print(f"    表达式: {FACTORS[name]}")
        try:
            row = evaluate_factor(df, name)
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
