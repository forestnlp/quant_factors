# -*- coding: utf-8 -*-
"""因子评估层（research 中间区）

来自 playground/factor_ic_ir_pipeline.py 与 factor_scan.py，提炼为通用能力：

    1. load_factor_data  — 用 Qlib DataHandlerLP 一次性加载多因子 + label
    2. winsorize_zscore — 按每日截面做缩尾 + 稳健标准化（无未来函数）
    3. evaluate_factor   — 单因子 IC/RankIC/ICIR 汇总
    4. scan_factors      — 批量评估并按 |RankICIR| 排序
    5. add_industry_columns / industry_neutral — 申万行业维度：附加行业派生列、
       按日×行业中位数去均值（剥离行业β，验因子真伪/增强信号）

用法：
    from research.factor_eval import load_factor_data, winsorize_zscore, evaluate_factor, scan_factors
"""

from pathlib import Path

import numpy as np
import pandas as pd

from research.config import industry_map_dir, qlib_uri

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


def split_is_oos(df: pd.DataFrame, split: str = "2025-08-01",
                 horizon: int = HORIZON) -> tuple[pd.DataFrame, pd.DataFrame]:
    """按时间轴切成样本内(IS)/样本外(OOS)两段，用于防过拟合筛选。

    IS 段末尾留空 horizon 天，避免 IS 因子的 label 跨过切点用到 OOS 的收益。
    只用时间切分，不重算任何统计量，因此两段各自仍是截面计算、无未来函数。
    """
    dt = df.index.get_level_values("datetime")
    cut = pd.Timestamp(split)
    is_end = cut - pd.tseries.offsets.BDay(horizon)
    is_df = df[dt < is_end]
    oos_df = df[dt >= cut]
    return is_df, oos_df


# ---------- 行业维度（申万一级，来源 data/industry_map/）----------

def _stock_to_industry() -> dict:
    """成分股快照 -> {qlib标的名(大写): 行业代码}。快照为准 PIT，仅用于中性化。"""
    p = industry_map_dir() / "stock_industry_l1.csv"
    if not p.exists():
        raise FileNotFoundError(f"缺少行业映射 {p}，先运行: python research/data_fetcher.py industry")
    m = pd.read_csv(p, dtype={"证券代码": str, "行业代码": str})
    m["行业代码"] = m["行业代码"].str.zfill(6)

    def to_qilib(c: str) -> str:
        c = str(c).zfill(6)
        if c[0] == "6":
            return "SH" + c
        if c[0] in "03":
            return "SZ" + c
        if c[0] in "489":
            return "BJ" + c
        return "SH" + c

    return dict(zip(m["证券代码"].map(to_qilib), m["行业代码"]))


def add_industry_columns(df: pd.DataFrame) -> pd.DataFrame:
    """为 load_factor_data 结果附加行业列（不破坏 MultiIndex）。

    附加列：_ind（行业代码）及 ind_mom_20 / ind_amt_ratio / ind_vol_20
    （行业 20 日动量、行业量能比 5/60、行业 20 日波动），
    供构造"个股相对行业"类复合因子；未映射到行业的标的不删除。
    """
    inst = df.index.get_level_values("instrument")
    s = pd.Series(inst, index=df.index).map(_stock_to_industry())
    df = df.assign(_ind=s.values)

    ind = pd.read_csv(industry_map_dir() / "sw_l1_index_daily.csv", dtype={"code": str})
    ind["dt"] = pd.to_datetime(ind["日期"])
    ind = ind.sort_values(["code", "dt"])
    g = ind.groupby("code")
    ind["ind_mom_20"] = g["收盘"].pct_change(20)
    ind["ind_amt_ratio"] = g["成交额"].transform(
        lambda x: x.rolling(5).mean() / x.rolling(60).mean())
    ind["ind_vol_20"] = g["收盘"].pct_change().rolling(20).std()
    key = ind[["dt", "code", "ind_mom_20", "ind_amt_ratio", "ind_vol_20"]]
    key = key.rename(columns={"dt": "datetime", "code": "_ind"})

    tmp = df[["_ind"]].reset_index().merge(key, on=["datetime", "_ind"], how="left")
    tmp = tmp.set_index(["datetime", "instrument"])
    for c in ["ind_mom_20", "ind_amt_ratio", "ind_vol_20"]:
        df[c] = tmp[c].reindex(df.index)
    return df


def industry_neutral(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """按 日×行业 中位数去均值，剥离行业β（需先 add_industry_columns）。

    与 winsorize_zscore 同理只用截面信息，无未来函数。返回副本。
    """
    if "_ind" not in df.columns:
        raise ValueError("请先调用 add_industry_columns 附加 _ind 列")
    df = df.copy()
    for col in columns:
        med = df.groupby(["datetime", "_ind"], observed=True)[col].transform("median")
        df[col] = df[col] - med
    return df
