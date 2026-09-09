# -*- coding: utf-8 -*-
"""分钟聚合 → 日内日频特征（P1 风向标战役）。

原料：data/raw/jq/min_agg/*.csv（云端聚合的开盘窗口量价，三窗 3m/30m/90m）。
产物：derived/alpha/<col>.parquet（alpha 契约 date/code/value 长表），
      eval / backtest / wfo 按名自动加载，无需改流水线。

特征全部用**窗口内自洽比值**（抽样月取数下无外部依赖，避免未来函数）：
  m_gap3     开盘3分钟涨幅 c3/o-1        —— 用户"开盘抢跑"直觉的直接度量
  m_gap30    前30分钟涨幅 c30/o-1        —— 定调强度
  m_pull30   30分钟内冲高回落 c30/h30-1  —— 冲高回落（≤0，越负越"假突破"）
  m_trend90  30→90分钟延续 c90/c30-1     —— 用户"前1.5小时决定一天性质"
  m_vconc3   前3分钟量占前90分钟比 v3/v90 —— 量能前置度（用户强调的量维度）
  m_vdecay30 前30量/后60量 v30/(v90-v30)  —— 量能衰减（>1=先放量为"抢跑"）
板块内领先度（风向标核心，行业 PIT 中性化）：
  m_lead30   m_gap30 在同申万一级行业内的截面分位（率先启动=板块内先动）

用法：conda run -n jaycode python -m research.build_min
"""

from __future__ import annotations

import glob

import numpy as np
import pandas as pd

from research.config import derived_dir, raw_dir

COLS = ["m_gap3", "m_gap30", "m_pull30", "m_trend90", "m_vconc3",
        "m_vdecay30", "m_lead30"]


def load_agg() -> pd.DataFrame:
    files = sorted(glob.glob(str(raw_dir("jq", "min_agg") / "min_agg_*.csv")))
    if not files:
        raise SystemExit("无 min_agg 分片，先跑: python -m research.fetch min_agg")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df.drop_duplicates(subset=["day", "code"])
    return df


def build(df: pd.DataFrame) -> pd.DataFrame:
    f = df.copy()
    o = f["o"].replace(0, np.nan)
    f["m_gap3"] = f["c3"] / o - 1
    f["m_gap30"] = f["c30"] / o - 1
    f["m_pull30"] = f["c30"] / f["h30"].replace(0, np.nan) - 1
    f["m_trend90"] = f["c90"] / f["c30"].replace(0, np.nan) - 1
    v90 = f["v90"].replace(0, np.nan)
    f["m_vconc3"] = f["v3"] / v90
    f["m_vdecay30"] = f["v30"] / (v90 - f["v30"]).replace(0, np.nan)
    # 板块内领先度：行业 PIT as-of（与 eval 同语义：季末快照向未来生效）
    ind = pd.read_parquet(derived_dir() / "industry.parquet")
    ind = ind[["date", "code", "sw_l1"]].rename(columns={"date": "snap"})
    ind["snap"] = pd.to_datetime(ind["snap"])
    f["dt"] = pd.to_datetime(f["day"])
    f = pd.merge_asof(
        f.sort_values("dt"), ind.sort_values("snap"), by="code",
        left_on="dt", right_on="snap", direction="backward")
    f["m_lead30"] = f.groupby(["day", "sw_l1"])["m_gap30"].rank(pct=True)
    return f[["day", "code"] + COLS].rename(columns={"day": "date"})


def main() -> None:
    f = build(load_agg())
    f["date"] = f["date"].astype(str)     # alpha 契约：date 与宽表同口径（str）
    for c in COLS:
        out = f[["date", "code", c]].dropna().rename(columns={c: "value"})
        p = derived_dir("alpha") / f"{c}.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(p, index=False)
        b = pd.read_parquet(p)            # 纪律 1：读回验证
        print(f"  {c:11s} rows={len(b):>8}  {b['date'].min()} ~ {b['date'].max()}"
              f"  mean={b['value'].mean():+.4f}")


if __name__ == "__main__":
    main()
