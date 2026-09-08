# -*- coding: utf-8 -*-
"""WFO 驱动器：滚动向前验证（验证协议 v2 的执行者）

两类产出：
  1. `years`：给定因子在其固定配置下**逐年**的成绩（年化/Sharpe/超额）——
     回答"这个规则是不是只在某几年灵"。
  2. `rotate`：**滚动年度选枪**——每年 Y 只用 Y 之前的数据从候选池里选
     Sharpe 最高者，然后看它 Y 年真实表现。回答"每年重新定规则 vs 一锤子"，
     以及"候选池里该选谁"。这是接近实盘的模拟（决策只用过去）。

预注册及格线（跑前定死，写进本文件）：
  - 因子级：逐年 Sharpe > 0 的年数 ≥ 4/6，且非单一年份贡献过半收益。
  - 轮换级：轮换组合的年化 ≥ 池内最优单因子（选枪动作本身要创造价值）。

用法：
    conda run -n jaycode python -m research.wfo years a_rev_x_lowvol --reverse
    conda run -n jaycode python -m research.wfo rotate a_rev_x_lowvol:rev a_quiet_two:rev
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from research import backtest as bt

YEARS = [2020, 2021, 2022, 2023, 2024, 2025, 2026]


def _stats(ret: pd.Series) -> dict:
    if len(ret) < 30:
        return {"ann": float("nan"), "sharpe": float("nan"),
                "ann_ex": float("nan")}
    ann = (1 + ret["ret"]).prod() ** (252 / len(ret)) - 1
    shp = ret["ret"].mean() / (ret["ret"].std() + 1e-12) * np.sqrt(252)
    ex = (ret["ret"] - ret["mkt"]).dropna()
    ann_ex = (1 + ex).prod() ** (252 / len(ex)) - 1
    return {"ann": float(ann), "sharpe": float(shp), "ann_ex": float(ann_ex)}


def _curve(col: str, k: int, rebal: int, reverse: bool,
           band: tuple[float, float]) -> pd.DataFrame:
    """跑一次组合回测，取回日收益曲线（含基准）。"""
    import os
    from research.config import derived_dir
    tmp = str(derived_dir("_wfo") / f"{col}.parquet")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    bt.RET_PATH = tmp
    bt.FEATURE_COLS = [col]
    bt.run(col, k, rebal, reverse=reverse, band=band, quiet=True)
    cur = pd.read_parquet(tmp)
    os.remove(tmp)
    bt.RET_PATH = None
    return cur


def cmd_years(a: argparse.Namespace) -> None:
    band = tuple(float(x) for x in a.band.split(","))
    cur = _curve(a.factor, a.k, a.rebal, a.reverse, band)
    print(f"=== WFO 逐年：{a.factor}（k={a.k} rebal={a.rebal} "
          f"band={band} {'多高值端' if a.reverse else '多低值端'} 含费）===")
    rows = []
    for y in YEARS:
        seg = cur[cur.index.year == y]
        s = _stats(seg)
        if np.isnan(s["sharpe"]):
            continue
        rows.append((y, s))
        print(f"  {y}  年化 {s['ann']:+7.1%}  Sharpe {s['sharpe']:+5.2f}  "
              f"超额 {s['ann_ex']:+7.1%}  ({len(seg)} 日)")
    pos = sum(1 for _, s in rows if s["sharpe"] > 0)
    print(f"  正 Sharpe 年数 {pos}/{len(rows)}  → 及格线 ≥4/6: "
          f"{'PASS' if pos >= 4 and len(rows) >= 5 else 'FAIL'}")
    all_s = _stats(cur)
    tot = np.prod([1 + s["ann"] for _, s in rows]) - 1
    top = max(rows, key=lambda r: r[1]["ann"])
    print(f"  全区间 {all_s['ann']:+.1%}/Sharpe {all_s['sharpe']:.2f}；"
          f"最佳单年 {top[0]} 贡献占比 "
          f"{top[1]['ann'] / tot:.0%}（应 <50%，否则=靠一年吃饭）")
    out = {"factor": a.factor, "years": {y: s for y, s in rows},
           "pos_years": pos, "n_years": len(rows), "full": all_s}
    print(json.dumps({"ok": True, **out}, ensure_ascii=False, default=str))


def cmd_rotate(a: argparse.Namespace) -> None:
    """每年用"去年成绩"选枪，看今年真实表现（决策只用过去）。"""
    cands = []
    for spec in a.factors:
        name, _, flag = spec.partition(":")
        cands.append((name, flag == "rev"))
    band = tuple(float(x) for x in a.band.split(","))
    curves = {n: _curve(n, a.k, a.rebal, rv, band) for n, rv in cands}
    picks = {}
    print(f"=== 滚动年度选枪（选枪依据=上一年 Sharpe，k={a.k} rebal={a.rebal}）===")
    parts = []
    for y in YEARS:
        if y == YEARS[0]:
            pick = cands[0][0]      # 第一年无历史，取池内首列（如实记账）
            tag = "无历史→默认"
        else:
            sc = {}
            for n, _ in cands:
                prev = curves[n][(curves[n].index.year == y - 1)]
                sc[n] = _stats(prev)["sharpe"]
            pick = max(sc, key=lambda n: (sc[n] if not np.isnan(sc[n]) else -9))
            tag = "上年 " + " ".join(f"{n}:{sc[n]:+.2f}" for n, _ in cands)
        picks[y] = pick
        seg = curves[pick][curves[pick].index.year == y]
        s = _stats(seg)
        parts.append(seg)
        print(f"  {y}  选 {pick:16s}（{tag}）→ 当年年化 {s['ann']:+7.1%} "
              f"Sharpe {s['sharpe']:+5.2f}")
    rot = pd.concat(parts)[["ret"]]
    rot["mkt"] = curves[cands[0][0]]["mkt"].reindex(rot.index)
    rs = _stats(rot)
    print(f"  轮换组合全区间：年化 {rs['ann']:+.1%}  Sharpe {rs['sharpe']:.2f}  "
          f"超额 {rs['ann_ex']:+.1%}")
    for n, _ in cands:
        s = _stats(curves[n])
        print(f"  [对照] 单用 {n:16s}：年化 {s['ann']:+.1%}  Sharpe {s['sharpe']:.2f}")
    print("  及格线：轮换 ≥ 池内最优单因子，否则选枪动作无价值（承认一锤子更优）")


def main() -> None:
    ap = argparse.ArgumentParser(description="WFO 滚动验证")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("years", help="因子逐年成绩")
    p1.add_argument("factor")
    p1.add_argument("-k", type=int, default=100)
    p1.add_argument("--rebal", type=int, default=10)
    p1.add_argument("--band", default="0.10,0.50")
    p1.add_argument("--reverse", action="store_true")
    p1.set_defaults(func=cmd_years)
    p2 = sub.add_parser("rotate", help="滚动年度选枪")
    p2.add_argument("factors", nargs="+", help="name[:rev] ...")
    p2.add_argument("-k", type=int, default=100)
    p2.add_argument("--rebal", type=int, default=10)
    p2.add_argument("--band", default="0.10,0.50")
    p2.set_defaults(func=cmd_rotate)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
