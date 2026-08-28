# -*- coding: utf-8 -*-
"""因子评估层（research 中间区）

来自 playground/factor_ic_ir_pipeline.py 与 factor_scan.py，提炼为通用能力：

    1. load_factor_data  — 用 Qlib DataHandlerLP 一次性加载多因子 + label
    2. winsorize_zscore — 按每日截面做缩尾 + 稳健标准化（无未来函数）
    3. evaluate_factor   — 单因子 IC/RankIC/ICIR 汇总
    4. scan_factors      — 批量评估并按 |RankICIR| 排序

用法：
    from research.factor_eval import load_factor_data, winsorize_zscore, evaluate_factor, scan_factors
"""

from pathlib import Path

import numpy as np
import pandas as pd

from research.config import qlib_uri

HORIZON = 5          # 默认未来 horizon 日收益作为 label
FREQ = "day"
INSTRUMENTS = "all"


def _load_env() -> dict:
    """读取 .env（供 qlib 初始化前设置重定向环境变量）。"""
    env = {}
    p = Path(__file__).resolve().parents[1] / ".env"
    if not p.exists():
        return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


def build_label(horizon: int = HORIZON) -> str:
    """构造未来 horizon 日收益作为 label（Qlib 表达式）。"""
    return f"Ref($close, -{horizon}) / $close - 1"


def load_factor_data(factor_exprs: list[str], factor_names: list[str],
                     horizon: int = HORIZON,
                     start_time: str = "2023-08-01",
                     end_time: str = "2026-08-06",
                     instruments: str = INSTRUMENTS,
                     provider_uri: Path | None = None) -> pd.DataFrame:
    """一次性加载多因子 + label，返回 MultiIndex (datetime, instrument)。

    行情读取截止到 end_time；末尾不足 horizon 天的样本因 label 为 NaN 被 Dropna 丢弃。
    """
    import qlib  # noqa: E402

    from qlib.data.dataset import DatasetH  # noqa: E402
    from qlib.data.dataset.handler import DataHandlerLP  # noqa: E402

    uri = Path(provider_uri or qlib_uri())
    qlib.init(provider_uri=str(uri), region="cn")

    label_expr = build_label(horizon)
    handler = DataHandlerLP(
        instruments=instruments,
        start_time=start_time,
        end_time=end_time,
        data_loader={
            "class": "QlibDataLoader",
            "kwargs": {"config": (factor_exprs + [label_expr], factor_names + ["y_future"])},
        },
        infer_processors=[{"class": "DropnaProcessor"}],
    )
    dataset = DatasetH(handler=handler, segments={"eval": (start_time, end_time)})
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
    from qlib.contrib.eva.alpha import calc_ic

    pred = df[name]
    label = df["y_future"]
    ic, ric = calc_ic(pred, label, dropna=True)

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


def scan_factors(df: pd.DataFrame, factors: dict[str, str]) -> pd.DataFrame:
    """批量评估因子并按 |RankICIR| 降序返回汇总表。

    参数：
        df:      load_factor_data 的返回结果。
        factors: {名字: Qlib表达式} 字典，与加载时传入保持一致。
    返回：
        排序后的 DataFrame（index=因子名）。
    """
    rows = []
    for name in factors:
        try:
            row = evaluate_factor(df, name)
            rows.append(row)
        except Exception as e:  # noqa: BLE001
            print(f"[失败] {name}: {e}")
    res = pd.DataFrame(rows).set_index("factor")
    res["abs_RankICIR"] = res["RankICIR"].abs()
    return res.sort_values("abs_RankICIR", ascending=False).drop(columns=["abs_RankICIR"])
