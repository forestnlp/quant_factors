# -*- coding: utf-8 -*-
"""ML 因子组合侦察演习：LightGBM 逐年向前合成信号 → 塞回 WFO 同口径回测。

定性（2026-09-10 用户批准"先试试效果"）：**侦察演习**，不是转正通道——
产物只落 data/derived/alpha/ml_lgbm.parquet，不入 factorlib 账本。
正式合成三战仍待预注册（池=100 支时，ML 与族折减等权同场竞技）。

口径纪律：
  - 特征 = 全体 candidate+product 因子的日截面 rank(pct)（LGBM 原生吃 NaN，
    新因子上市晚的覆盖稀疏天然兼容）
  - 标签 = fwd_ret_5 的日截面 rank(pct)（与调仓周期一致，纪律8）
  - 逐年向前：测试年 Y ∈ 2022..2026，训练窗 = 起点~(Y年-12天)，
    留 12 天隔离带防 5 日标签跨窗泄漏；模型永远见不到测试年
  - 回测 = wfo._curve 同款（k=100 rebal=10 band(0.10,0.50]，多高分端）
    → 数字与 wfo_screen.jsonl 全体单枪直接可比（假想敌 a_small_value 0.78）

用法：
    conda run -n jaycode python -m research.ml_combo
产物：derived/alpha/ml_lgbm.parquet + 打印逐年成绩（日志 data/derived/ml_combo.log）
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import lightgbm as lgb

from research import alpha, eval as ev, factorlib, wfo
from research.config import derived_dir

TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
PURGE = pd.Timedelta(days=12)      # 5 交易日标签 + 缓冲的隔离带
LGB = dict(objective="regression", n_estimators=400, learning_rate=0.05,
           num_leaves=63, min_child_samples=10000, feature_fraction=0.7,
           bagging_fraction=0.8, bagging_freq=5, seed=42, n_jobs=-1,
           verbose=-1)


def build() -> tuple[pd.DataFrame, np.ndarray, np.ndarray, list[str]]:
    """评估样本（可交易+厚截面）× 全体在册因子截面 rank → (dt, X, y, names)。"""
    lib = factorlib.load()
    names = [n for n, r in lib["factors"].items()
             if r["status"] in ("candidate", "product")]
    f, _ = ev.load()
    wide = set(pq.ParquetFile(derived_dir() / "features.parquet")
               .schema_arrow.names)
    mi = pd.MultiIndex.from_arrays([f["date"].values, f["code"].values])
    cols = {}
    for i, n in enumerate(names, 1):
        if n in wide:
            s = f[n]
        else:
            p = alpha.alpha_dir() / f"{n}.parquet"
            if not p.exists():
                from research.wfo_screen import ensure_col
                ensure_col(n, lib["factors"][n]["expr"], wide)
            s = pd.read_parquet(p).set_index(["date", "code"])["value"]
            if not s.index.is_unique:
                s = s[~s.index.duplicated()]
            s = s.reindex(mi).values
        # 日截面 pct-rank（NaN 保留；LGBM 原生处理缺失）
        cols[n] = pd.Series(s, index=f.index).astype("float32")
        if i % 10 == 0:
            print(f"  特征 {i}/{len(names)}", flush=True)
    X = pd.DataFrame(cols)
    dts = f["dt"].values
    grp = pd.Series(dts, index=f.index)
    X = X.groupby(grp).rank(pct=True).astype("float32")
    y = f.groupby("dt")[ev.LABEL].rank(pct=True).astype("float32").values
    return f, X.to_numpy(), y, names


def main() -> None:
    print("== ml_combo 侦察演习：LightGBM 逐年向前 ==", flush=True)
    f, X, y, feat_names = build()
    dt = pd.to_datetime(f["dt"])
    pred = np.full(len(f), np.nan, dtype="float32")
    for yr in TEST_YEARS:
        t0 = pd.Timestamp(year=yr, month=1, day=1)
        tr = ((dt < t0 - PURGE) & np.isfinite(y)).to_numpy()
        te = (dt.dt.year == yr).to_numpy()   # 只预测本年（防后年模型覆写泄漏）
        m = lgb.LGBMRegressor(**LGB)
        m.fit(X[tr], y[tr], feature_name=feat_names)
        pred[te] = m.predict(X[te]).astype("float32")
        tr_d, te_d = dt[tr].max().date(), f"{dt[te].min().date()}~{dt[te].max().date()}"
        print(f"  {yr}: 训练 {tr.sum():,} 行（截至 {tr_d}，留隔离带）"
              f"→ 预测 {te.sum():,} 行（{te_d}）", flush=True)
    out = f.assign(p=pred)
    chk = out[out["p"].notna()]
    p = alpha.alpha_dir() / "ml_lgbm.parquet"
    chk[["date", "code", "p"]].rename(columns={"p": "value"}
                                      ).to_parquet(p, index=False)
    print(f"合成信号落盘 {p}（{len(chk):,} 行，"
          f"{chk['date'].min()}~{chk['date'].max()}）", flush=True)

    # 信号体检：测试段逐日 RankIC（预测 vs 实际 5 日收益；先 rank 后 Pearson=Spearman）
    ranks = chk.groupby("dt")[["p", ev.LABEL]].rank()
    ric = ranks.groupby(chk["dt"].values).apply(
        lambda g: g["p"].corr(g[ev.LABEL])).dropna()
    icir = float(ric.mean() / (ric.std() + 1e-12) * np.sqrt(252 / 5))
    print(f"合成信号逐日 RankIC 均值 {ric.mean():+.4f}"
          f"（ICIR年化≈{icir:+.2f}，正率 {(ric > 0).mean():.0%}）", flush=True)

    # 回测：与全体单枪同口径（wfo_screen 判决文件里的 full_sharpe 直接可比）
    cur = wfo._curve("ml_lgbm", 100, 10, reverse=True, band=(0.10, 0.50))
    rows = []
    for yr in wfo.YEARS:
        seg = cur[cur.index.year == yr]
        s = wfo._stats(seg)
        if not np.isnan(s["sharpe"]):
            rows.append((yr, s))
            print(f"  {yr}  年化 {s['ann']:+7.1%}  Sharpe {s['sharpe']:+5.2f}  "
                  f"超额 {s['ann_ex']:+7.1%}", flush=True)
    full = wfo._stats(cur)
    pos = sum(1 for _, s in rows if s["sharpe"] > 0)
    tot = float(np.prod([1 + s["ann"] for _, s in rows]) - 1)
    top_y, top = max(rows, key=lambda r: r[1]["ann"])
    share = top["ann"] / tot if tot > 0 else float("nan")
    print(f"\n=== ml_lgbm 全区间（含费）：年化 {full['ann']:+.1%}  "
          f"Sharpe {full['sharpe']:.2f} ===")
    print(f"  正 Sharpe {pos}/{len(rows)} 年；最佳单年 {top_y} 贡献 {share:.0%}"
          f"（WFO 及格线：≥4 正 且 <50%）")
    print("  假想敌（wfo_screen 在册单枪头名）对照见下")

    import json
    scr = [json.loads(l) for l in
           open(derived_dir() / "wfo_screen.jsonl", encoding="utf-8")]
    scr.sort(key=lambda r: -(r.get("full_sharpe") or -9))
    for r in scr[:5]:
        print(f"    {r['factor']:26s} 全区间 Sharpe {r['full_sharpe']:+.2f} "
              f"年化 {r['full_ann']:+.1%}")


if __name__ == "__main__":
    main()
