# -*- coding: utf-8 -*-
"""候选大清洗：全部 candidate 批量过 WFO（滚动向前验证）。

背景（2026-09-10 候选通胀）：dig 的 IS 及格线（0.46）按单发人工审设计，
机器 7×24 轰炸后失效——44 候选按运气也该有十几个"IS 过线"。本脚本用
产品转正的同一道 WFO 门（预注册、写死于 wfo.py）逐一重审：
  及格 = 正 Sharpe 年数 ≥4/6 且 最佳单年贡献 <50%
口径 = dig 组合终裁同配置：k=100 rebal=10 band(0.10,0.50]，
方向与 IS/neu RankIC 符号强制联动（IC>0 → reverse 多高值端）。

只判决、不改状态——清洗结果人工过目后用 factorlib set-status 执行。

用法：
    conda run -n jaycode python -m research.wfo_screen            # 全部 candidate
    conda run -n jaycode python -m research.wfo_screen n1 n2 ...  # 指定名单
产物：data/derived/wfo_screen.jsonl（每因子一行判决，可断点续跑）
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from research import alpha
from research import eval as ev
from research import factorlib, wfo
from research.config import derived_dir

OUT = derived_dir() / "wfo_screen.jsonl"


def ensure_col(name: str, expr: str, wide_cols: set[str]) -> None:
    """保证因子列可加载：宽表列直接有，否则要求/补齐 alpha 编译产物。"""
    if name in wide_cols:
        return
    p = alpha.alpha_dir() / f"{name}.parquet"
    if not p.exists():
        long = alpha.compile_expr(name, expr)
        long.to_parquet(p, index=False)


def is_ric(f: pd.DataFrame, name: str) -> float | None:
    """IS/neu RankIC（方向联动依据，与 dig judge 同契约）。"""
    st = ev.evaluate(ev._attach(f, name), name)
    seg = st.get("IS/neu") or {}
    return seg.get("RankIC")


def screen_one(f: pd.DataFrame, name: str, rec: dict,
               wide_cols: set[str]) -> dict:
    ensure_col(name, rec["expr"], wide_cols)
    ric = None
    bt_str = rec.get("backtest")
    if isinstance(bt_str, str):           # dig 存过 is_view JSON → 直接取符号
        try:
            ric = json.loads(bt_str).get("IS_RankIC")
        except (json.JSONDecodeError, AttributeError):
            ric = None
    if ric is None:                        # 人工时代候选 → 现算
        ric = is_ric(f, name)
    if ric is None:
        return {"factor": name, "verdict": "FAIL", "why": "IS RankIC 不可得"}
    reverse = bool(ric > 0)
    cur = wfo._curve(name, 100, 10, reverse, (0.10, 0.50))
    rows = []
    for y in wfo.YEARS:
        seg = cur[cur.index.year == y]
        s = wfo._stats(seg)
        if not np.isnan(s["sharpe"]):
            rows.append((y, s))
    n = len(rows)
    pos = sum(1 for _, s in rows if s["sharpe"] > 0)
    tot = float(np.prod([1 + s["ann"] for _, s in rows]) - 1) if rows else 0.0
    top_y, top = max(rows, key=lambda r: r[1]["ann"]) if rows else (None, None)
    share = float(top["ann"] / tot) if rows and tot > 0 else float("nan")
    full = wfo._stats(cur)
    ok = pos >= 4 and n >= 5 and not (share >= 0.5)
    years = {y: round(s["sharpe"], 2) for y, s in rows}
    return {"factor": name, "IS_RankIC": round(ric, 4), "reverse": reverse,
            "years": years, "pos": pos, "n": n, "top_year": top_y,
            "top_share": round(share, 2), "full_ann": round(full["ann"], 4),
            "full_sharpe": round(full["sharpe"], 3),
            "verdict": "PASS" if ok else "FAIL",
            "why": f"正{pos}/{n}年 最佳{top_y}占{share:.0%}"
                   f" 全区间{full['ann']:+.1%}/Shp{full['sharpe']:.2f}"}


def main() -> None:
    lib = factorlib.load()
    names = sys.argv[1:] or [n for n, r in lib["factors"].items()
                             if r["status"] == "candidate"]
    done = set()
    if OUT.exists():
        for ln in OUT.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(ln)["factor"])
            except (json.JSONDecodeError, KeyError):
                pass
    import pyarrow.parquet as pq
    wide_cols = set(pq.ParquetFile(derived_dir() / "features.parquet")
                    .schema_arrow.names)
    f, _ = ev.load()
    print(f"待清洗 {len(names)} 个（已完成 {len(done)}），开跑", flush=True)
    for i, name in enumerate(names, 1):
        if name in done:
            continue
        try:
            r = screen_one(f, name, lib["factors"][name], wide_cols)
        except Exception as e:            # 单因子编译/回测崩：记 FAIL 继续跑
            r = {"factor": name, "verdict": "ERROR", "why": f"{type(e).__name__}: {e}"}
        with open(OUT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[{i}/{len(names)}] {name:32s} {r['verdict']:4s} {r.get('why','')}",
              flush=True)
    print("=== 清洗完毕 ===", flush=True)


if __name__ == "__main__":
    main()
