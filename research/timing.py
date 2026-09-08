# -*- coding: utf-8 -*-
"""仓位择时层（预注册 2026-09-08）：等权指数均线开关，叠加在 Top-K 产品上

无融券世界里唯一的防守手段：大盘走弱就降仓吃现金，走强再满仓。

规则（预注册写死，跑后不许改）：
  - 信号：等权指数（与 backtest 基准同口径）收盘 > MA(N) → 满仓，否则降到 off 档。
  - PIT：t 日收盘算信号、t+1 日生效（敞口与费用都 shift(1)）；均线暖机期无信号=空仓。
  - 闲置现金按 0 收益（保守，不计逆回购）；档位切换按 |Δ仓| × FEE/2 计费
    （开→关→开 整周期 = 一个往返，与底层调仓费各算各的）。
  - 网格 N∈{20,60,120} × off∈{0, 0.5} 共 6 组一次跑完；**选优只看 IS Sharpe**，
    网格阶段物理屏蔽全区间/OOS 输出；若 6 组 IS 全低于无择时基线 → 关闭择时层。
  - 验收（当选配置一次定，IS 选完后才放全区间）：①全区间年化 > 基线
    ②最大回撤优于基线 ③WFO 逐年及格（正 Sharpe ≥4 且最佳单年贡献 <50%）
    ——三项同改善才算过，否则判死。

用法：
    conda run -n jaycode python -m research.timing a_rev_x_lowvol \
        -k 10 --rebal 10 --reverse --band 0.10,0.50 --base-is 0.79
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from research.backtest import FEE
from research.eval import SPLIT
from research.wfo import _curve, _stats, YEARS

NS = [20, 60, 120]
OFFS = [0.0, 0.5]


def overlay(cur: pd.DataFrame, n: int, off: float) -> pd.DataFrame:
    """把 MA(n)/off 择时叠加到底仓日收益曲线上，返回同结构的定时曲线。"""
    idx = (1 + cur["mkt"]).cumprod()
    sig = idx > idx.rolling(n).mean()          # 暖机期 NaN 比较为 False → off
    exp = pd.Series(np.where(sig, 1.0, off), index=cur.index).shift(1)
    exp = exp.fillna(off)                      # 首日无昨日信号 → 空仓起步
    cost = exp.diff().abs().fillna(0.0) * FEE / 2
    ret = exp * cur["ret"] - cost
    return pd.DataFrame({"ret": ret, "mkt": cur["mkt"]})


def main() -> None:
    ap = argparse.ArgumentParser(description="仓位择时网格（只看 IS 选优）")
    ap.add_argument("factor")
    ap.add_argument("-k", type=int, default=10)
    ap.add_argument("--rebal", type=int, default=10)
    ap.add_argument("--band", default="0.10,0.50")
    ap.add_argument("--reverse", action="store_true")
    ap.add_argument("--base-is", type=float, required=True,
                    help="无择时基线的 IS Sharpe（选优对照线）")
    a = ap.parse_args()

    band = tuple(float(x) for x in a.band.split(","))
    cur = _curve(a.factor, a.k, a.rebal, a.reverse, band)
    split = pd.Timestamp(SPLIT)
    base_is = _stats(cur[cur.index < split])
    print(f"=== 择时网格：{a.factor} k={a.k} rebal={a.rebal} band={band}"
          f"{' 多高值端' if a.reverse else ''} 含费 ===")
    print(f"  [无择时基线] IS 年化 {base_is['ann']:+.1%}  Sharpe "
          f"{base_is['sharpe']:.2f}（选优对照线 {a.base_is:.2f}）")

    best = None
    for n in NS:
        for off in OFFS:
            t = overlay(cur, n, off)
            s = _stats(t[t.index < split])
            tag = "满仓→空仓" if off == 0 else f"满仓→半仓({off:.0%})"
            print(f"  MA{n:>3d} off={off:.1f}（{tag}）  IS 年化 {s['ann']:+7.1%} "
                  f"IS Sharpe {s['sharpe']:+5.2f}")
            if best is None or s["sharpe"] > best[1]["sharpe"]:
                best = ((n, off), s, t)

    (n, off), s_is, t = best
    print(f"  → IS 当选：MA{n} off={off}（IS Sharpe {s_is['sharpe']:.2f}）")
    if s_is["sharpe"] <= a.base_is:
        print("  判决：6 组 IS 全不过基线 → 择时层关闭（预注册分支）")
        return

    # IS 选优完成，才放全区间与逐年（一次验收）
    full = _stats(t)
    pv = (1 + t["ret"]).cumprod()
    dd = float((pv / pv.cummax() - 1).min())
    print(f"  [全区间验收] 年化 {full['ann']:+.1%}  Sharpe {full['sharpe']:.2f}  "
          f"最大回撤 {dd:+.1%}")
    rows = []
    for y in YEARS:
        seg = t[t.index.year == y]
        s = _stats(seg)
        if np.isnan(s["sharpe"]):
            continue
        rows.append((y, s))
        print(f"    {y}  年化 {s['ann']:+7.1%}  Sharpe {s['sharpe']:+5.2f}  "
              f"超额 {s['ann_ex']:+7.1%}")
    pos = sum(1 for _, s in rows if s["sharpe"] > 0)
    tot = np.prod([1 + s["ann"] for _, s in rows]) - 1
    top = max(rows, key=lambda r: r[1]["ann"])
    contrib = top[1]["ann"] / tot
    ok = (full["ann"] > 0.138 and dd > -0.342 and pos >= 4 and contrib < 0.5)
    print(f"  正 Sharpe 年数 {pos}/{len(rows)}；最佳单年 {top[0]} 贡献 "
          f"{contrib:.0%}")
    print("  及格线：年化>+13.8% 且 回撤优于-34.2% 且 WFO 两线达标 → "
          f"{'PASS 择时层采纳' if ok else 'FAIL 择时层判死'}")


if __name__ == "__main__":
    main()
