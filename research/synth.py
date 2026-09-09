# -*- coding: utf-8 -*-
"""多因子合成器：把若干已验证因子拧成一支合成枪（L4 合成战役工具）。

方法（事前定死，不做花活）：
  每个成员 → 全市场逐日截面 rank 百分位 → 按方向对齐（rev=IC>0 者高分好；
  非 rev 者取 1-rank）→ 逐日截面 z-score → 按族权重求和 → 合成值。
  族折减：成员用 "|" 分族，同族内部均分"一支枪"的权重（防同原料刷分）。

产物对齐 alpha 契约：写 derived/alpha/<out>.parquet（date/code/value 长表），
backtest / eval / wfo 均可把 <out> 当普通因子列直接用。

用法：
    conda run -n jaycode python -m research.synth build a_synth1 \
        --members "a_rev_x_lowvol:rev|a_qiet_main_inflow:rev,a_main_vwap_quiet:rev"
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from research import alpha as al
from research.config import derived_dir


def _load_member(name: str) -> pd.DataFrame:
    """成员因子 → 宽表（index=date, columns=code）。宽表列或 alpha 产物皆可。"""
    cols = al.wide_columns()
    if name in cols:
        df = pd.read_parquet(al.wide_path(), columns=["date", "code", name])
    else:
        p = derived_dir("alpha") / f"{name}.parquet"
        if not p.exists():
            raise SystemExit(f"成员 {name} 既不在宽表也无 alpha 产物（先 alpha compile）")
        df = pd.read_parquet(p).rename(columns={"value": name})
    df["date"] = pd.to_datetime(df["date"])
    return df.pivot(index="date", columns="code", values=name)


def _rank_z(w: pd.DataFrame, reverse: bool) -> pd.DataFrame:
    """逐日截面 rank 百分位 → 方向对齐 → 逐日 z-score。"""
    r = w.rank(axis=1, pct=True)
    if not reverse:
        r = 1.0 - r
    mu, sd = r.mean(axis=1), r.std(axis=1)
    return r.sub(mu, axis=0).div(sd + 1e-12, axis=0)


def cmd_build(a: argparse.Namespace) -> None:
    fams = []
    for grp in a.members.split("|"):
        fam = []
        for spec in grp.split(","):
            name, _, flag = spec.strip().partition(":")
            fam.append((name, flag == "rev"))
        fams.append(fam)
    total = len(fams)
    parts = []
    for fam in fams:
        w_each = 1.0 / total / len(fam)          # 族折减：同族均分一支枪的权重
        for name, rev in fam:
            z = _rank_z(_load_member(name), rev) * w_each
            parts.append(z)
            print(f"  成员 {name:28s} {'rev' if rev else 'fwd'} "
                  f"权重 {w_each:.3f}")
    score = sum(parts)
    long = (score.stack().rename("value").reset_index()
            .rename(columns={"level_1": "code"}))
    # alpha 契约：date 与宽表同口径（str），backtest/eval merge 依赖此类型
    long["date"] = pd.to_datetime(long["date"]).dt.strftime("%Y-%m-%d")
    p = derived_dir("alpha") / f"{a.out}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    long.to_parquet(p, index=False)
    back = pd.read_parquet(p)                     # 纪律 1：读回验证
    print(json.dumps({"ok": True, "out": a.out, "rows": len(back),
                      "date_min": str(back["date"].min().date()),
                      "date_max": str(back["date"].max().date()),
                      "nan_ratio": round(float(back["value"].isna().mean()), 4)},
                     ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(description="多因子等权合成（族折减）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("build", help="合成并落 alpha 契约产物")
    p1.add_argument("out", help="合成因子名（产物列名）")
    p1.add_argument("--members", required=True,
                    help="name[:rev] 逗号分隔，族间用 | 分隔（同族折减一支枪权重）")
    p1.set_defaults(func=cmd_build)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
