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

import argparse
import glob

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import lightgbm as lgb

from research import alpha, eval as ev, factorlib, wfo
from research.config import derived_dir, raw_dir

TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
PURGE = pd.Timedelta(days=12)      # 5 交易日标签 + 缓冲的隔离带
BAND_CUR = (0.10, 0.50)            # 现行选择带（band 战役维持原样）
BAND_OPEN = (0.0, 1.0)             # 归因臂：全开（结论35：只用于归因，非候选形态）
OFFICIAL = ["alpha_016", "alpha_088", "alpha_013", "alpha_044", "alpha_040",
            "alpha_015", "alpha_027", "alpha_050", "alpha_055", "alpha_003",
            "alpha_026", "alpha_012", "alpha_081", "alpha_094", "alpha_004"]
LGB = dict(objective="regression", n_estimators=400, learning_rate=0.05,
           num_leaves=63, min_child_samples=10000, feature_fraction=0.7,
           bagging_fraction=0.8, bagging_freq=5, seed=42, n_jobs=-1,
           verbose=-1)
# XGBoost 对照臂超参（2026-09-17 用户点名试 XGB）：与 LGB 等强度对齐——
# max_depth=6≈num_leaves63；min_child_weight=10000≈min_child_samples（回归
# hessian=1 时同义）；subsample/colsample 对应 bagging/feature_fraction。
XGB = dict(objective="reg:squarederror", n_estimators=400, learning_rate=0.05,
           max_depth=6, min_child_weight=10000, subsample=0.8,
           colsample_bytree=0.7, tree_method="hist", seed=42, n_jobs=-1)


def consolidate_top15() -> None:
    """raw/jq/alpha_ref/top15_alpha101_*.csv → derived/alpha/alpha_XXX.parquet。

    官方原值直取件（B 腿）合片：列名即官方 alpha 名，落成长表后与既有
    编译产物同构（date/code/value），build() 走同一条 reindex 通道进特征池。
    读回验证（rules#4/#9）：总行数、区间、逐列非 NaN 率、边界重复值一致性。
    """
    files = sorted(glob.glob(str(raw_dir("jq", "alpha_ref")
                                 / "top15_alpha101_*.csv")))
    if not files:
        raise SystemExit("无 top15 分片，先跑 fetch_alpha --tag top15")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    dup = df.duplicated(subset=["day", "code"], keep=False)
    if dup.any():   # 分片边界重叠须值一致，否则是数据事故
        bad = (df[dup].groupby(["day", "code"])[OFFICIAL]
               .nunique().gt(1).any().any())
        if bad:
            raise SystemExit(f"分片边界值冲突（{int(dup.sum())} 行），拒收")
    df = df.drop_duplicates(subset=["day", "code"]).rename(columns={"day": "date"})
    print(f"合并 {len(files)} 片: {len(df):,} 行 "
          f"{df['date'].min()}~{df['date'].max()}", flush=True)
    for c in OFFICIAL:
        out = df[["date", "code", c]].rename(columns={c: "value"})
        out = out[out["value"].notna()]
        out.to_parquet(alpha.alpha_dir() / f"{c}.parquet", index=False)
        print(f"  {c}: {len(out):,} 行 "
              f"({len(out) / len(df):.0%} 非空, {out['date'].min()}"
              f"~{out['date'].max()})", flush=True)


def build(extra_cols: tuple[str, ...] = ()) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, list[str]]:
    """评估样本（可交易+厚截面）× 全体在册因子截面 rank → (dt, X, y, names)。
    extra_cols：宽表里的原料列（如 ind_*/unl_*）直接当特征，不经账本。"""
    lib = factorlib.load()
    names = [n for n, r in lib["factors"].items()
             if r["status"] in ("candidate", "product")]
    f, _ = ev.load()
    wide = set(pq.ParquetFile(derived_dir() / "features.parquet")
               .schema_arrow.names)
    # 原料直用（红线圈外：原料进特征≠帮因子过闸）+ 官方原值件（alpha_*.parquet）
    names += [c for c in extra_cols
              if c in wide or (alpha.alpha_dir() / f"{c}.parquet").exists()]
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


def _mk(model: str):
    """模型工厂：lgb=现役基线；xgb=等强度对照臂（用户点名，超参见 XGB 注释）。"""
    if model == "xgb":
        import xgboost as xgb
        return xgb.XGBRegressor(**XGB)
    return lgb.LGBMRegressor(**LGB)


def _train_arm(X: np.ndarray, y: np.ndarray, dt: pd.Series,
               names: list[str], tag: str, f: pd.DataFrame,
               model: str = "lgb") -> pd.DataFrame:
    """单臂逐年向前训练+预测，信号落 derived/alpha/<tag>.parquet，返回预测表。"""
    pred = np.full(len(f), np.nan, dtype="float32")
    imp_sum = np.zeros(len(names))
    for yr in TEST_YEARS:
        t0 = pd.Timestamp(year=yr, month=1, day=1)
        tr = ((dt < t0 - PURGE) & np.isfinite(y)).to_numpy()
        te = (dt.dt.year == yr).to_numpy()   # 只预测本年（防后年模型覆写泄漏）
        m = _mk(model)
        if model == "lgb":
            m.fit(X[tr], y[tr], feature_name=names)   # lgb 支持具名特征
        else:
            m.fit(X[tr], y[tr])                        # xgb.fit 无 feature_name
        pred[te] = m.predict(X[te]).astype("float32")
        if model == "lgb":
            imp_sum += m.booster_.feature_importance("gain")
        else:
            imp_sum += np.asarray(m.feature_importances_)
        print(f"  {tag} {yr}: 训练 {tr.sum():,} 行（截至 {dt[tr].max().date()}"
              f"）→ 预测 {te.sum():,} 行", flush=True)
    imp = pd.Series(imp_sum, index=names).sort_values(ascending=False)
    off_rank = [(n, int(imp.index.get_loc(n)) + 1) for n in OFFICIAL
                if n in imp.index]
    print(f"  {tag} 官方列 importance 名次: "
          + ", ".join(f"{n}#{r}" for n, r in sorted(off_rank, key=lambda t: t[1])),
          flush=True)
    out = f.assign(p=pred)
    chk = out[out["p"].notna()]
    chk[["date", "code", "p"]].rename(columns={"p": "value"}
                                      ).to_parquet(alpha.alpha_dir() / f"{tag}.parquet",
                                                   index=False)
    # 信号体检：测试段逐日 RankIC（预测 vs 实际 5 日收益）
    ranks = chk.groupby("dt")[["p", ev.LABEL]].rank()
    ric = ranks.groupby(chk["dt"].values).apply(
        lambda g: g["p"].corr(g[ev.LABEL])).dropna()
    print(f"  {tag} RankIC {ric.mean():+.4f}（正率 {(ric > 0).mean():.0%}）",
          flush=True)
    return chk


def battle() -> None:
    """收编判决役：同池单变量——特征池 ±官方Top15，双模型 × 双 band 四格。

    归因逻辑（结论35 教训：band 裁判规则可能吃掉新信号的 alpha）：
      - 主判据 = 现行 band(0.10,0.50] 下 ±官方 的同窗差（对照 0.72 基线口径）
      - 归因格 = band 全开：若增益只在全开臂显形 → band 重审的又一条证据
        （全开非候选形态，结论35 已关闭该路线，此格只做归因不产生改线效力）
    及格参考（HANDOFF#18 跑前写死）：RankIC 破 0.1149 平台；同窗 2022 起
    对照基线 +16.3%/0.72。侦察定性，产物不入账本，数字照实报。
    """
    print("== 收编判决役：±官方 Top15 双臂 ==")
    consolidate_top15()
    f, X, y, names = build(OFFICIAL)
    base_idx = [i for i, n in enumerate(names) if n not in OFFICIAL]
    print(f"特征池: 在册 {len(base_idx)} + 官方 {len(names) - len(base_idx)}"
          f" = {len(names)}", flush=True)
    dt = pd.to_datetime(f["dt"])
    arms = {
        "mlb_base": _train_arm(X[:, base_idx], y, dt,
                               [names[i] for i in base_idx], "mlb_base", f),
        "mlb_off": _train_arm(X, y, dt, names, "mlb_off", f),
    }
    for tag in arms:
        for band, bname in ((BAND_CUR, "现行band"), (BAND_OPEN, "全开")):
            cur = wfo._curve(tag, 100, 10, reverse=True, band=band)
            win = cur[cur.index.year >= 2022]
            sf, sw = wfo._stats(cur), wfo._stats(win)
            yrs = " ".join(
                f"{yr}:{wfo._stats(cur[cur.index.year == yr])['sharpe']:+.2f}"
                for yr in (2022, 2023, 2024, 2025, 2026))
            print(f"  {tag:9s} {bname:8s} 全区间 {sf['ann']:+6.1%}/{sf['sharpe']:.2f}"
                  f" | 同窗2022+ {sw['ann']:+6.1%}/{sw['sharpe']:.2f} | {yrs}",
                  flush=True)


def main() -> None:
    import json
    ap = argparse.ArgumentParser(description="ML 组合侦察（LightGBM 逐年向前）")
    ap.add_argument("--model", default="lgb", choices=["lgb", "xgb"],
                    help="组合器：lgb=现役基线；xgb=对照臂（同池同种子）")
    ap.add_argument("--extra", default="",
                    help="逗号分隔的宽表原料列或官方 alpha 列，直接当特征")
    ap.add_argument("--tag", default="ml_lgbm",
                    help="产物/回测信号名（对照组用不同 tag，勿覆盖基线）")
    ap.add_argument("--consolidate", action="store_true",
                    help="只做 top15 合片+读回验证，不训练")
    ap.add_argument("--battle", action="store_true",
                    help="收编判决役：±官方 Top15 双臂 × 双 band 四格")
    a = ap.parse_args()
    if a.consolidate:
        consolidate_top15()
        return
    if a.battle:
        battle()
        return
    extra = tuple(c.strip() for c in a.extra.split(",") if c.strip())
    print(f"== ml_combo 侦察演习：LightGBM 逐年向前（tag={a.tag}"
          f"，原料直用 {len(extra)} 列）==", flush=True)
    f, X, y, feat_names = build(extra)
    dt = pd.to_datetime(f["dt"])
    pred = np.full(len(f), np.nan, dtype="float32")
    for yr in TEST_YEARS:
        t0 = pd.Timestamp(year=yr, month=1, day=1)
        tr = ((dt < t0 - PURGE) & np.isfinite(y)).to_numpy()
        te = (dt.dt.year == yr).to_numpy()   # 只预测本年（防后年模型覆写泄漏）
        m = _mk(a.model)
        if a.model == "lgb":
            m.fit(X[tr], y[tr], feature_name=feat_names)
        else:
            m.fit(X[tr], y[tr])
        pred[te] = m.predict(X[te]).astype("float32")
        tr_d, te_d = dt[tr].max().date(), f"{dt[te].min().date()}~{dt[te].max().date()}"
        print(f"  {yr}: 训练 {tr.sum():,} 行（截至 {tr_d}，留隔离带）"
              f"→ 预测 {te.sum():,} 行（{te_d}）", flush=True)
    out = f.assign(p=pred)
    chk = out[out["p"].notna()]
    p = alpha.alpha_dir() / f"{a.tag}.parquet"
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
    cur = wfo._curve(a.tag, 100, 10, reverse=True, band=(0.10, 0.50))
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
