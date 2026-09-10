# -*- coding: utf-8 -*-
"""L3 评估层：因子裁判（读 derived 宽表，只读不写）

对给定因子列输出：
    截面 IC / RankIC / ICIR / IC 正率（对 fwd_ret_5，按日截面）
    五分层日均收益与多空价差
    行业中性化版本（日 × 行业中位数去均值）
    IS / OOS 双段（默认 2024-01-01 切，OOS 为纯未见过样本）

PIT 与口径纪律：
    - 剔除 paused / ST / 涨跌停触板样本（实盘不可交易）
    - 截面样本数 < MIN_CS 的交易日丢弃（早年截面太薄，IC 噪声大）
    - 行业归属用 as-of（季末快照向前取最近一期），不用未来分类

用法：
    conda run -n jaycode python -m research.eval                 # 跑默认基线因子集
    conda run -n jaycode python -m research.eval v_amt_5_20 ...  # 指定因子
    conda run -n jaycode python -m research.eval --json a_xxx    # 机器可读（L4 工具契约）

    因子列可来自宽表，也可来自 alpha 编译器产物（derived/alpha/<name>.parquet，
    按名字自动加载并 join）。--json 时每因子输出一行 JSON，NaN 转 null。
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from research.config import derived_dir

SPLIT = "2024-01-01"      # IS/OOS 切点（IS 2020~2023，OOS 2024~今）
MIN_CS = 300              # 单日截面最少样本数
LABEL = "fwd_ret_5"

BASELINE = ["r_20d", "v_amt_5_20", "v_std_20", "v_corr_pv_20",
            "vlm_ln_mv", "vlm_turnover", "mf_net_pct_main",
            "auc_imb", "auc_money_share", "mt_fin_ratio", "bb_yest"]


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    """宽表 + 行业维表（as-of 对齐到日频）。"""
    f = pd.read_parquet(derived_dir() / "features.parquet")
    f = f[f["paused"].fillna(1) == 0]
    f = f[f["st_flag"].fillna(0) == 0]
    # 涨停触板剔除（买不进）：high_limit 为哨兵值 10000 的退市整理期不剔除
    ok = (f["high_limit"] < 9000) & (f["close"] < f["high_limit"] - 1e-6)
    f = f[ok | f["high_limit"].isna()]

    ind = pd.read_parquet(derived_dir() / "industry.parquet")
    ind = ind[["date", "code", "sw_l1"]].rename(columns={"date": "snap"})
    f["dt"] = pd.to_datetime(f["date"])
    ind["snap"] = pd.to_datetime(ind["snap"])
    f = _asof_industry(f, ind)
    # 截面厚度门槛：早年/尾部交易日样本过薄，IC 噪声主导，整日剔除
    cnt = f.groupby("dt")["code"].transform("size")
    return f[cnt >= MIN_CS], ind


def _asof_industry(f: pd.DataFrame, ind: pd.DataFrame) -> pd.DataFrame:
    """按 code 分组做 as-of：每个交易日取最近一期（不超过当日）的行业快照。"""
    f = f.sort_values("dt").reset_index(drop=True)
    ind = ind.sort_values("snap")
    out = pd.merge_asof(
        f, ind[["code", "snap", "sw_l1"]].rename(columns={"snap": "dt"}),
        on="dt", by="code", direction="backward",
        tolerance=pd.Timedelta(days=120))
    return out


def neutralize(f: pd.DataFrame, col: str) -> pd.Series:
    """行业中性化：同日同业内中位数去均值（稳健，不假设正态）。"""
    x = f.groupby(["dt", "sw_l1"])[col].transform("median")
    return f[col] - x


def _cs_stats(f: pd.DataFrame, col: str) -> pd.DataFrame:
    """按日截面算 Pearson IC 与 Spearman RankIC。"""
    sub = f[["dt", "code", col, LABEL]].dropna()
    g = sub.groupby("dt")
    ic = g.apply(lambda x: x[col].corr(x[LABEL]), include_groups=False)
    ric = g.apply(lambda x: x[col].rank().corr(x[LABEL].rank()),
                  include_groups=False)
    return pd.DataFrame({"ic": ic, "ric": ric})


def _quantiles(f: pd.DataFrame, col: str, n: int = 5) -> pd.Series:
    """五分层日均收益，返回各层均值（升序：Q1 最低 … Q5 最高）。"""
    sub = f[["dt", col, LABEL]].dropna()
    q = sub.groupby("dt")[col].transform(
        lambda s: pd.qcut(s.rank(method="first"), n, labels=False,
                          duplicates="drop"))  # 极端日有效值<n 时并层（2026-09-10 修：否则 qcut 崩整批）
    m = sub.assign(q=q).groupby("q")[LABEL].mean()
    return m


def evaluate(f: pd.DataFrame, col: str) -> dict:
    """一个因子的完整体检：全样本 / IS / OOS × 原始 / 行业中性。"""
    res = {}
    for seg, sub in _segments(f):
        if sub.empty:
            continue          # 空段（如短窗口无 IS 样本）直接跳过
        for tag, series in (("raw", sub[col]), ("neu", neutralize(sub, col))):
            s = sub.assign(_x=series)
            st = _cs_stats(s, "_x")
            if st.empty:
                continue
            q = _quantiles(s, "_x")
            key = f"{seg}/{tag}"
            res[key] = {
                "RankIC": st["ric"].mean(),
                "ICIR": st["ric"].mean() / (st["ric"].std() + 1e-12),
                "pos%": (st["ric"] > 0).mean(),
                "days": len(st),
                "LS": q.iloc[-1] - q.iloc[0] if len(q) == 5 else np.nan,
            }
    return res


def _segments(f: pd.DataFrame):
    yield "full", f
    yield "IS", f[f["dt"] < pd.Timestamp(SPLIT)]
    yield "OOS", f[f["dt"] >= pd.Timestamp(SPLIT)
                   + pd.Timedelta(days=7)]   # 标签空隙（5 交易日≈7 自然日）


def _attach(f: pd.DataFrame, col: str) -> pd.DataFrame:
    """请求的列不在宽表时，尝试从 alpha 编译器产物加载（date/code/value 长表）。"""
    if col in f.columns:
        return f
    p = derived_dir("alpha") / f"{col}.parquet"
    if not p.exists():
        return f
    a = pd.read_parquet(p).rename(columns={"value": col})
    return f.merge(a[["date", "code", col]], on=["date", "code"], how="left")


def _jsonable(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def main() -> None:
    import sys

    args = sys.argv[1:]
    as_json = "--json" in args
    cols = [x for x in args if x != "--json"] or BASELINE
    f, _ = load()
    if not as_json:
        print(f"评估样本: {len(f)} 行, {f['dt'].nunique()} 天, "
              f"切点 IS<{SPLIT}<=OOS, 截面下限 {MIN_CS}")
        hdr = f"{'因子':18s} {'段/中性':9s} {'RankIC':>8s} {'ICIR':>7s} " \
              f"{'pos%':>6s} {'LS(bp)':>8s} {'天数':>5s}"
        print(hdr)
        print("-" * len(hdr))
    for c in cols:
        f = _attach(f, c)
        if c not in f.columns:
            if as_json:
                print(json.dumps({"ok": False, "factor": c,
                                  "error": "宽表与 alpha 产物中均不存在"},
                                 ensure_ascii=False))
            else:
                print(f"{c}: 宽表中不存在，跳过")
            continue
        r = evaluate(f, c)
        if as_json:
            out = {"ok": True, "factor": c, "label": LABEL,
                   "split": SPLIT,
                   "segments": {k: {kk: _jsonable(vv) for kk, vv in v.items()}
                                for k, v in r.items()}}
            print(json.dumps(out, ensure_ascii=False))
            continue
        for seg in ("full/raw", "full/neu", "IS/raw", "OOS/raw", "OOS/neu"):
            if seg not in r:
                continue
            v = r[seg]
            print(f"{c:18s} {seg:9s} {v['RankIC']:+8.4f} {v['ICIR']:+7.3f} "
                  f"{v['pos%']:6.3f} {v['LS'] * 1e4:+8.1f} {v['days']:5d}")
        print()


if __name__ == "__main__":
    main()
