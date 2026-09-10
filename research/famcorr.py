# -*- coding: utf-8 -*-
"""候选家族血缘测量：全体 candidate+product 的日截面秩相关矩阵。

用途（2026-09-10 清洗后取舍）：43/44 候选过了 WFO——逐年考试筛不掉同族，
病灶是"一族枪各自都灵、相互无新信息"。本脚本量出每支枪与最近血缘、
与在役产品的秩相关，供"留谁并谁"决策。

算法：抽日（每 3 日取 1）→ alpha 产物一次性 merge 进样本 → 一次 pivot 成
 (日×code, 因子) 宽块 → 逐日截面百分位秩 + 47×47 相关 → 逐对取跨日最大
 绝对值（Spearman 语义，pairwise 完整观测，与 dig 换皮闸同一姿势）。

产物：data/derived/famcorr.json
  {name: {"max_corr": x, "max_with": n, "corr_product": y}}  逐枪摘要
用法：conda run -n jaycode python -m research.famcorr
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research import alpha, eval as ev, factorlib
from research.config import derived_dir

SAMPLE_STEP = 3        # 每 3 天抽 1 天算截面秩（估计足够稳）


def main() -> None:
    lib = factorlib.load()
    names = sorted(n for n, r in lib["factors"].items()
                   if r["status"] in ("candidate", "product"))
    prods = [n for n in names if lib["factors"][n]["status"] == "product"]
    f, _ = ev.load()
    days = np.sort(f["dt"].unique())[::SAMPLE_STEP]
    sub = f[f["dt"].isin(days)].copy()
    print(f"{len(names)} 支枪 × {len(days)} 抽样日，编译对齐中...", flush=True)
    for n in names:                      # 宽表没有的 → merge alpha 编译产物
        if n not in sub.columns:
            p = alpha.alpha_dir() / f"{n}.parquet"
            if not p.exists():
                raise SystemExit(f"{n} 无 alpha 产物（先 wfo_screen）")
            sub = sub.merge(pd.read_parquet(p).rename(columns={"value": n}),
                            on=["date", "code"], how="left")
    rk = {n: sub.pivot(index="dt", columns="code", values=n)
             .rank(axis=1, pct=True) for n in names}
    print("逐日截面秩 + 全矩阵相关...", flush=True)
    acc = np.zeros((len(names), len(names)))
    n_day_used = 0
    for d in days:
        X = pd.DataFrame(np.column_stack([rk[n].loc[d].values for n in names]),
                         columns=names)
        # 教训（首跑虚高）：早期因子覆盖只有几十只票 → 小截面伪相关冲到 ±1。
        # 与 dig.max_corr 同保护：只用全因子齐值的完整截面，且 <300 只跳过。
        X = X.dropna()
        if len(X) < 300:
            continue
        n_day_used += 1
        c = np.abs(X.corr().values)
        acc = np.fmax(acc, np.nan_to_num(c, nan=0.0))
    print(f"有效截面 {n_day_used}/{len(days)} 天", flush=True)
    acc[np.diag_indices_from(acc)] = 0.0
    C = pd.DataFrame(acc, index=names, columns=names)
    out = {}
    for n in names:
        if lib["factors"][n]["status"] == "product":
            continue
        row = C.loc[n].drop(n)
        out[n] = {"max_corr": round(float(row.max()), 3),
                  "max_with": str(row.idxmax()),
                  "corr_product": round(float(C.loc[n, prods].max()), 3)}
    (derived_dir() / "famcorr.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("=== 逐枪：与最近血缘 / 与在役产品（按血缘远近）===", flush=True)
    for n, r in sorted(out.items(), key=lambda kv: -kv[1]["max_corr"]):
        print(f"{n:34s} 血缘 {r['max_corr']:.2f} ← {r['max_with']:30s} "
              f"产品距离 {r['corr_product']:.2f}", flush=True)


if __name__ == "__main__":
    main()
