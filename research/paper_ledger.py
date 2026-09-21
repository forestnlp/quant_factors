# -*- coding: utf-8 -*-
"""纸面实盘账本（收尾战役①，2026-09-21 用户批准；同日重构，见下）。

**为什么重构（2026-09-21 对账闸当场抓获信号换代）**：初版账本按役55 A1 重放，
对账闸不吻合——排查证实 mlb_xgb.parquet 已于 09-20 15:32 被干净池重训覆盖
（基线转正既定动作），役55 归档分属旧信号版本、已不可复现；A1 叠加规则在
当前官方信号上重放仅 +1.0%/0.14（役58 版本脆弱性教训复发）。教训固化：
**账本不得重新实现战法**——重放=另一套代码=漂移温床。

现设计（简单优先、零再实现）：净值曲线直接调官方引擎 `wfo._curve`（与判决
同一条代码），账本只做落盘+读回+两轨对照：
  - product_k10_r10  现役产品形态（ML Top-10、每 10 交易日）
  - shadow_k10_r20   役60 影子轨（ML Top-10、每 20 交易日，转正候选）
产物 derived/paper_ledger/{tag}_nav.csv（逐日净值）+ {tag}_trades.csv
（调仓日持仓名单）。每晚 nightly.sh 自动重放（数据纯函数，幂等）。

公允性口径：立账日 2026-09-21 之前=历史重放（引擎验证用）；之后的行才是
真·样本外成绩，汇报时两口径分开。**信号换代须在本账本备注版本**（本次
mlb_xgb 版本日期见 VERSION_NOTE 常量，从文件 mtime 自动读）。

用法：conda run -n jaycode python -m research.paper_ledger
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd

from research.config import derived_dir
from research.wfo import _curve, _stats

BAND, K = (0.10, 0.50), 10
TRACKS = {"product_k10_r10": 10, "shadow_k10_r20": 20}   # tag -> rebal


def _sig_version() -> str:
    p = derived_dir("alpha") / "mlb_xgb.parquet"
    return datetime.fromtimestamp(os.path.getmtime(p)).strftime("%F %H:%M")


def topk_lists(rebal: int) -> pd.DataFrame:
    """调仓日持仓名单：与回测同口径（band 内按分取前 K），供人工核单。"""
    sig = pd.read_parquet(derived_dir("alpha") / "mlb_xgb.parquet")
    ft = pd.read_parquet(derived_dir() / "features.parquet",
                         columns=["date", "code", "paused", "st_flag",
                                  "close", "high_limit"])
    tr = ((ft["paused"].fillna(1) == 0) & (ft["st_flag"] == 0)
          & ((ft["high_limit"] >= 9000) & (ft["high_limit"] != 10000)
             | (ft["close"] < ft["high_limit"] - 1e-6))).fillna(False)
    u = ft[tr][["date", "code"]].merge(
        sig.rename(columns={"value": "sc"}), on=["date", "code"], how="inner")
    days = sorted(u["date"].unique())[::rebal]
    rows = []
    for d in days:
        day = u[u["date"] == d]
        q = day["sc"].rank(ascending=False, method="first") / len(day)
        sel = day[(q >= BAND[0]) & (q <= BAND[1])] \
            .sort_values("sc", ascending=False).head(K)
        for rk, (_, r) in enumerate(sel.iterrows(), 1):
            rows.append({"date": pd.Timestamp(d).date().isoformat(),
                         "rank": rk, "code": r["code"],
                         "score": round(float(r["sc"]), 4)})
    return pd.DataFrame(rows)


def main() -> None:
    out = derived_dir("paper_ledger")
    os.makedirs(out, exist_ok=True)
    ver = _sig_version()
    print(f"信号版本 mlb_xgb.parquet mtime = {ver}（换代须核对此值）")

    stats = {}
    for tag, rebal in TRACKS.items():
        cur = _curve("mlb_xgb", K, rebal, True, BAND)   # 官方引擎，唯一实现
        nav = (1 + cur["ret"]).cumprod()
        dd = float((nav / nav.cummax() - 1).min())
        s_all, s_22 = _stats(cur), _stats(cur[cur.index >= "2022-01-01"])
        stats[tag] = (s_all, s_22)
        nav.rename("nav").to_frame().to_csv(f"{out}/{tag}_nav.csv")
        topk_lists(rebal).to_csv(f"{out}/{tag}_trades.csv", index=False)
        print(f"[{tag}] 全区间 年化 {s_all['ann']:+.1%}/Shp {s_all['sharpe']:.2f}"
              f"/dd {dd:.1%}"
              f" | 同窗 {s_22['ann']:+.1%}/{s_22['sharpe']:.2f}"
              f" | nav 至 {nav.index[-1]} = {nav.iloc[-1]:.3f}")

    # 两轨差（役60 预期：影子 r20 ≥ 现役 r10）
    pa, sa = stats["product_k10_r10"][0], stats["shadow_k10_r20"][0]
    print(f"两轨年化差 {sa['ann'] - pa['ann']:+.1%}（役60 预期方向：影子≥现役）")

    # 读回验证（rules#1）
    for tag in TRACKS:
        n = pd.read_csv(f"{out}/{tag}_nav.csv")
        t = pd.read_csv(f"{out}/{tag}_trades.csv")
        assert len(n) > 1500 and len(t) > 100, f"{tag} 读回行数异常"
        print(f"读回 {tag}: nav {len(n)} 行（末值 {n['nav'].iloc[-1]:.3f}）"
              f"| trades {len(t)} 行（末调仓日 {t['date'].iloc[-1]}）")
    print("账本落盘 OK")


if __name__ == "__main__":
    main()
