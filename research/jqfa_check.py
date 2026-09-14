# -*- coding: utf-8 -*-
"""聚宽同款因子评估对表：本地跑开源 jqfactor_analyzer 1.1.0（聚宽"因子评估"
页同款引擎），对比我方 eval 指标差多少。

定性：**对表体检**，不是转正通道，不改任何账本。因子与行情全程本地，
不向聚宽云上传任何内容（规则 8）——聚宽仅作为"评估算法"来源，非数据通道。

隔离：jqfa 依赖老栈（pandas 2.x/numpy 1.x），严禁装进 jaycode 主环境；
用 .tools/jqfa-venv（项目内 venv，gitignore）。

口径差（对表时必须注明，否则是冤枉任何一方）：
  - 价格 = raw 层日线 close（不复权）；jqfa 端分红日会产生假收益噪声
  - jqfa = 全市场分层（quantiles=5）；我方 eval = 可交易过滤 + band k 篮子
  - jqfa IC 对齐期 = T+period 收盘；我方 RankIC 同 T+5——可比
  - 我方产品是"高分为多"；jqfa 分层末位=因子值最高组，看末层年化即多头腿

用法：
    .tools/jqfa-venv/bin/python -m research.jqfa_check
产物：打印三样枪 jqfa 指标（日志 data/derived/jqfa_check.log）
"""

from __future__ import annotations

import glob
import json

import numpy as np
import pandas as pd
import jqfactor_analyzer.prepare as _P

SAMPLE = ["a_rev_x_lowvol", "a_small_value", "a_low_volume_return_chase"]
START, END = "2021-01-01", "2026-09-08"


def _quantize_factor(factor_data, quantiles=None, bins=None,
                     by_group=False, no_raise=True, zero_aware=False):
    """jqfa 原版 quantize_factor 的 pandas≥2.2 兼容替代（算法一字未改：
    逐日 pd.qcut 分位 + 1）。原版 groupby(外部键数组).apply 在 pandas 2.2
    会把分组键重复拼进结果索引（2 层→3 层）而崩——即 09-14 实测的
    "Length of new_levels (3) must be <= self.nlevels (2)"。此处手动按日
    循环 concat，索引保持 (date, asset) 两层。"""
    parts = []
    for _, x in factor_data.groupby(level="date")["factor"]:
        try:
            parts.append(pd.qcut(x, quantiles, labels=False) + 1)
        except Exception:
            if not no_raise:
                raise
            parts.append(pd.Series(index=x.index, dtype=float))
    fq = pd.concat(parts) if parts else pd.Series(dtype=float)
    fq.name = "factor_quantile"
    return fq.dropna()


_P.quantize_factor = _quantize_factor   # 猴子补丁（仅本进程生效）
from jqfactor_analyzer import FactorAnalyzer  # noqa: E402  须在补丁后导入


def quantile_returns(fac: pd.Series, px: pd.DataFrame) -> dict:
    """jqfa 分层算法的直算版（其 mean_return_by_quantile API 在 pandas 2.2
    下索引/权重列连崩，09-14 两次修补仍不通——算法本身极简，直算更可靠）：
    逐日 qcut 5 层 + T 日对 T→T+5 收益分层取均值，年化×252/5。"""
    fwd = px.pct_change(5).shift(-5).stack().rename("fr")   # T→T+5 收益
    fwd.index = fwd.index.set_names(["date", "asset"])
    df = pd.concat([fac.rename("f"), fwd], axis=1).dropna()
    q = df.groupby(level="date")["f"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates="drop") + 1)
    df = df.assign(q=q)
    mr = df.groupby(["date", "q"])["fr"].mean().unstack("q")
    ann5 = mr.mean() * (252 / 5)          # 重叠 5 日收益 → 年化（jqfa 同义）
    return {"q5_ann": float(ann5.get(5, np.nan)),
            "q1_ann": float(ann5.get(1, np.nan)),
            "ls_ann": float(ann5.get(5, np.nan) - ann5.get(1, np.nan))}


def load_prices() -> pd.DataFrame:
    """raw 层日线 close 透视（宽表同区间）。"""
    frames = []
    for p in sorted(glob.glob("data/raw/jq/daily/daily_*.csv")):
        d = pd.read_csv(p, usecols=["time", "code", "close"])
        d = d[(d["time"] >= START) & (d["time"] <= END)]
        if len(d):
            frames.append(d)
    px = pd.concat(frames, ignore_index=True).pivot(
        index="time", columns="code", values="close").sort_index()
    px.index = pd.to_datetime(px.index)
    px.index.name, px.columns.name = "date", "asset"
    return px


def load_factor(name: str) -> pd.Series:
    """已编译因子列 → jqfa 要的 MultiIndex(date, asset) Series。"""
    s = pd.read_parquet(f"data/derived/alpha/{name}.parquet")
    s = s[(s["date"] >= START) & (s["date"] <= END)].copy()
    s["date"] = pd.to_datetime(s["date"])
    idx = pd.MultiIndex.from_arrays([s["date"], s["code"]],
                                    names=["date", "asset"])
    return pd.Series(s["value"].values, index=idx).sort_index()


def main() -> None:
    px = load_prices()
    print(f"prices: {px.shape[0]} 交易日 × {px.shape[1]} 标的 "
          f"{px.index.min().date()}~{px.index.max().date()}", flush=True)
    out = {}
    for name in SAMPLE:
        fac = load_factor(name)
        # IC：jqfa 引擎（补丁①后其 IC 链实测可用；逐日 spearman=T+5 远期收益）
        fa = FactorAnalyzer(fac, px, weights=None, quantiles=5,
                            periods=(5,), max_loss=0.5)
        ic = fa.calc_factor_information_coefficient().dropna()
        v = ic["period_5"]
        ic_mean = float(v.mean())
        icir = float(v.mean() / (v.std() + 1e-12) * np.sqrt(252 / 5))
        # 分层收益：直算版（理由见 quantile_returns docstring）
        q = quantile_returns(fac, px)
        out[name] = dict(ic=round(ic_mean, 4), icir=round(icir, 2), **{
            k: round(x, 4) for k, x in q.items()})
        print(f"  {name:26s} IC {ic_mean:+.4f}  ICIR {icir:+.2f}  "
              f"末层年化 {q['q5_ann']:+.1%}  多空(末-首) {q['ls_ann']:+.1%}",
              flush=True)
    p = "data/derived/jqfa_check.json"
    json.dump(out, open(p, "w"), ensure_ascii=False, indent=1)
    print(f"落盘 {p}", flush=True)


if __name__ == "__main__":
    main()
