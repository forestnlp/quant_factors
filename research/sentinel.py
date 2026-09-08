# -*- coding: utf-8 -*-
"""淘汰哨兵（L4 工具契约层）：在库因子的近期健康复测

因子会失效（v_corr_pv_20 窗口翻转实证过）。库里的因子不能入库一次管永远：
用"最近 RECENT_DAYS 个交易日"的滚动窗口复算 RankIC，与入库时全历史基准对比，
方向翻转或强度衰减到地板以下 → 告警并建议降级 retired。

判据（对 neutral 口径，与入库评审同口径）：
    die   : 近期 RankIC 与全历史同号相反（sign 翻转）
    decay : |近期 ICIR| < max(DECAY_FLOOR, DECAY_RATIO × |入库 ICIR|)
    ok    : 其余

用法：
    conda run -n jaycode python -m research.sentinel            # 复测 candidate+product
    conda run -n jaycode python -m research.sentinel --apply     # 判 die 的自动转 retired 并记因
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from research import eval as ev
from research import factorlib

RECENT_DAYS = 250         # 近期窗口 ≈ 一年
DECAY_FLOOR = 0.10        # 近期 ICIR 绝对值地板
DECAY_RATIO = 0.35        # 或衰减到入库 ICIR 的 35% 以下


def judge(rec: dict, recent: dict) -> tuple[str, str]:
    """返回 (verdict, 说明)。recent: 近段 full/neu 指标。"""
    base = rec.get("eval") or {}
    ric_all, icir_all = base.get("ric_neu_full"), base.get("icir_neu_full")
    ric_r, icir_r = recent.get("RankIC"), recent.get("ICIR")
    if ric_r is None or ric_all is None:
        return "skip", "缺基准或近段数据"
    if ric_all * ric_r < 0:
        return "die", f"方向翻转：全历史 {ric_all:+.4f} → 近段 {ric_r:+.4f}"
    floor = max(DECAY_FLOOR, DECAY_RATIO * abs(icir_all or 0))
    if icir_r is not None and abs(icir_r) < floor:
        return "decay", (f"强度衰减：近段 ICIR {icir_r:+.3f} < 地板 {floor:.3f}"
                         f"（入库 {icir_all:+.3f}）")
    return "ok", f"近段 ICIR {icir_r:+.3f} 健康"


def main() -> None:
    ap = argparse.ArgumentParser(description="在库因子近期健康复测")
    ap.add_argument("--apply", action="store_true",
                    help="判 die 的自动 retired（默认只告警）")
    a = ap.parse_args()

    lib = factorlib.load()
    watch = {n: r for n, r in lib["factors"].items()
             if r["status"] in ("candidate", "product")}
    if not watch:
        print(json.dumps({"ok": True, "checked": 0,
                          "note": "库中无在评因子"}, ensure_ascii=False))
        return

    f, _ = ev.load()
    # 近段 = 最后 RECENT_DAYS 个交易日（按日历倒数，不用日历日乘法——
    # 否则窗口内日历日不足会被 MIN_CS 门槛整日剔除，只剩零头甚至崩）
    days = np.sort(f["dt"].unique())
    cut = days[-min(RECENT_DAYS, len(days))]
    recent_f = f[f["dt"] >= cut]
    print(f"哨兵复测 {len(watch)} 个因子，近段窗口起点="
          f"{pd.Timestamp(cut).date()}（{recent_f['dt'].nunique()} 交易日）")

    alerts = []
    for n, rec in watch.items():
        f2 = ev._attach(recent_f, n)
        if n not in f2.columns:
            alerts.append({"name": n, "verdict": "skip",
                           "msg": "因子数据缺失（alpha 产物被删？）"})
            continue
        st = ev.evaluate(f2, n).get("full/neu")
        verdict, msg = judge(rec, st or {})
        alerts.append({"name": n, "verdict": verdict, "msg": msg})
        if verdict == "die" and a.apply:
            factorlib.cmd_set_status(lib, n, "retired", f"哨兵判死：{msg}")

    bad = [x for x in alerts if x["verdict"] in ("die", "decay")]
    print(json.dumps({"ok": not bad, "checked": len(watch),
                      "alerts": alerts}, ensure_ascii=False, indent=1))
    if bad:
        raise SystemExit(2)      # 非零退出=有事发生，供调度/上层感知


if __name__ == "__main__":
    main()
