# -*- coding: utf-8 -*-
"""每日荐股层（产品二）：输出当前应持仓清单与买卖动作。

纪律：选股直接调用 backtest.topk_weights——与回测**同一个实现**（教训 2），
调仓日为全局序列 dates[::rebal]，与 +13.8%/0.66 那份回测逐票一致。
持仓是数据的纯函数（无状态文件）：全量权重矩阵取最后两个调仓行，
差额 = 买入/卖出动作，杜绝"脚本自己记账记歪"。

执行口径（诚实声明）：回测按信号日收盘价成交；实盘只能次日竞价/尾盘下单，
存在约 1 日漂移，不在回测里修饰，实盘以实测漂移为准。

用法：
    conda run -n jaycode python -m research.signals              # 现役产品默认参数
    conda run -n jaycode python -m research.signals --json       # 机器可读
"""

from __future__ import annotations

import argparse
import json

import pandas as pd

from research import alpha as al
from research import backtest as bt
from research import factorlib
from research.config import derived_dir

# 产品参数 = 精选度战役预注册定档（结论19/20）：Top-10、10 日调仓、带内选
DEFAULT = dict(col="a_rev_x_lowvol", k=10, rebal=10,
               reverse=True, band=(0.10, 0.50))


def _refresh_alpha(col: str) -> None:
    """alpha 产物是编译时点快照，宽表重建后不自动跟新（09-09 发现的滞后缺口）。
    荐股前核对：产物截止 < 宽表截止 且 因子在账本有表达式 → 自动重编译。"""
    if col in al.wide_columns():
        return                          # 宽表列天然最新，无需管
    p = derived_dir("alpha") / f"{col}.parquet"
    wmax = str(pd.read_parquet(al.wide_path(), columns=["date"])["date"].max())
    amax = (str(pd.read_parquet(p, columns=["date"])["date"].max())
            if p.exists() else "")
    if amax >= wmax:
        return
    lib = factorlib.load()
    expr = lib["factors"].get(col, {}).get("expr")
    if not expr:
        raise SystemExit(f"因子 {col} 产物停在 {amax or '∅'} < 宽表 {wmax}，"
                         f"且账本无表达式可重编译——先 alpha compile")
    print(f"[refresh] 产物 {amax} 落后宽表 {wmax}，按账本表达式重编译 {col} …")
    long = al.compile_expr(col, expr)   # 产物可从宽表重建，非原始层，允许覆盖
    long.to_parquet(p, index=False)


def build(col: str, k: int, rebal: int, reverse: bool,
          band: tuple[float, float]) -> dict:
    _refresh_alpha(col)                  # 产物滞后宽表 → 先重编译（防旧因子出旧单）
    bt.FEATURE_COLS = [col]            # load_pivots 按此加载（宽表列或 alpha 产物）
    _, tradable, feat = bt.load_pivots()
    w = bt.topk_weights(feat, col, k, tradable, rebal,
                        reverse=reverse, band=band)
    rows = w.dropna(how="all")
    asof = w.index[-1]
    sig_day = rows.index[-1]
    cur = rows.iloc[-1]
    prev = rows.iloc[-2] if len(rows) > 1 else pd.Series(dtype=float)
    held = sorted(cur[cur > 0].index)
    old = sorted(prev[prev > 0].index)
    score = feat[feat["date"] == sig_day].set_index("code")[col]
    return {
        "factor": col, "params": {"k": k, "rebal": rebal,
                                  "reverse": reverse, "band": list(band)},
        "data_asof": str(asof.date()),          # 数据截止日（收盘定稿日）
        "signal_day": str(sig_day.date()),      # 最近一个调仓日
        "is_rebal_now": str(sig_day.date()) == str(asof.date()),
        "hold": [{"code": c, "score": round(float(score.get(c, float("nan"))), 4)}
                 for c in held],
        "buy": [c for c in held if c not in old],
        "sell": [c for c in old if c not in cur.index[cur > 0].tolist()],
        "keep": [c for c in old if c in held],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="每日荐股（复用回测选股实现）")
    ap.add_argument("--col", default=DEFAULT["col"])
    ap.add_argument("-k", type=int, default=DEFAULT["k"])
    ap.add_argument("--rebal", type=int, default=DEFAULT["rebal"])
    ap.add_argument("--no-reverse", action="store_true",
                    help="因子高值端为差（默认做多高值端）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    r = build(a.col, a.k, a.rebal, not a.no_reverse, DEFAULT["band"])
    p = derived_dir("signals") / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(r, ensure_ascii=False, indent=1))

    if a.json:
        print(json.dumps(r, ensure_ascii=False))
        return
    tag = "【今天恰是调仓日】" if r["is_rebal_now"] else \
          f"（最近调仓日 {r['signal_day']}，未到调仓日则维持持仓）"
    print(f"因子 {r['factor']}  数据截止 {r['data_asof']} {tag}")
    print(f"应持有 {len(r['hold'])} 只（等权）：")
    for h in r["hold"]:
        mark = " ←新买入" if h["code"] in r["buy"] else ""
        print(f"  {h['code']}  因子值 {h['score']:+.4f}{mark}")
    if r["sell"]:
        print("应卖出：", ", ".join(r["sell"]))
    print(f"[存] {p}")


if __name__ == "__main__":
    main()
