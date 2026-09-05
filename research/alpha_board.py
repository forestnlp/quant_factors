# -*- coding: utf-8 -*-
"""alpha101 官方基线榜单（对答案，LLM 挖掘的参照系）

数据：raw/jq/alpha_ref/（聚宽 get_all_alpha_values 全市场，5 日采样 324 天）。
口径：与 eval.py 完全一致——可交易过滤（load）+ fwd_ret_5 + 日截面 RankIC +
     IS/OOS（OOS 留 7 自然日标签空隙）；采样日每 5 交易日一个，与 fwd_ret_5
     视野天然对齐、无重叠污染，ICIR 不做 √5 折算直接横向对比。
实现：pivot 日×票矩阵后按行掩码向量化算秩相关，82 因子一遍过。

用法：
    conda run -n jaycode python -m research.alpha_board
输出：derived/alpha_board.csv + 控制台摘要（榜单按 |IS ICIR| 排序防未来函数视角）
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.config import derived_dir, raw_dir
from research.eval import SPLIT, LABEL, load

RAW = raw_dir("jq", "alpha_ref")
GAP = pd.Timedelta(days=7)      # 标签空隙（5 交易日≈7 自然日），与 eval 同
OWN = ["v_amt_5_20", "vlm_turnover", "auc_money_share", "r_20d", "v_std_20"]


def _row_corr(a: pd.DataFrame, b: pd.DataFrame) -> pd.Series:
    """两个对齐矩阵按行算 Pearson（NaN 掩码；行内有效样本 <300 记 NaN）。"""
    m = a.notna() & b.notna()
    x = a.where(m).fillna(0.0).to_numpy(float)
    y = b.where(m).fillna(0.0).to_numpy(float)
    n = np.maximum(m.to_numpy().sum(1), 1)
    mx, my = x.sum(1) / n, y.sum(1) / n
    cov = (x * y).sum(1) / n - mx * my
    vx = (x * x).sum(1) / n - mx ** 2
    vy = (y * y).sum(1) / n - my ** 2
    r = cov / np.sqrt(vx * vy + 1e-18)
    return pd.Series(np.where(m.to_numpy().sum(1) >= 300, r, np.nan),
                     index=a.index)


def main() -> None:
    files = sorted(RAW.glob("alpha101_*.csv"))
    alphas = [f"alpha_{i:03d}" for i in range(1, 102)]
    a = pd.concat([pd.read_csv(p, usecols=["day", "code", *alphas],
                               dtype={"code": str}) for p in files],
                  ignore_index=True)
    a["dt"] = pd.to_datetime(a["day"])
    a = a.drop_duplicates(["dt", "code"])

    f, _ind = load()   # eval 同款可交易过滤 + 截面厚度门槛
    m = a.merge(f[["dt", "code", LABEL, *OWN]], on=["dt", "code"], how="inner")
    print(f"alpha 行 {len(a):,} → join 可交易样本 {len(m):,}，"
          f"采样日 {m['dt'].nunique()} 个")

    lab = m.pivot(index="dt", columns="code", values=LABEL)

    ric = {}
    for c in alphas + OWN:
        x = m.pivot(index="dt", columns="code", values=c)
        ok = x.notna() & lab.notna()
        # 掩码内重排秩（1..n 连续）→ 掩码外置 0 → 均值/方差项集合严格一致
        X = x.where(ok).rank(axis=1).fillna(0.0).to_numpy(float)
        Y = lab.where(ok).rank(axis=1).fillna(0.0).to_numpy(float)
        n = np.maximum(ok.to_numpy().sum(1), 1)
        mx, my = X.sum(1) / n, Y.sum(1) / n
        cov = (X * Y).sum(1) / n - mx * my
        vx = (X * X).sum(1) / n - mx ** 2
        vy = (Y * Y).sum(1) / n - my ** 2
        r = cov / np.sqrt(vx * vy + 1e-18)
        ric[c] = pd.Series(np.where(ok.to_numpy().sum(1) >= 300, r, np.nan),
                           index=x.index)
    R = pd.DataFrame(ric)

    # 自检：随机采样日与标准 pandas 秩相关对照（教训：产物必须先与基准证据核对）
    chk_day = R.index[len(R) // 2]
    row = m[m["dt"] == chk_day]
    c0 = "alpha_016"
    s = row[[c0, LABEL]].dropna()
    std = s[c0].rank().corr(s[LABEL].rank())
    mine = R.loc[chk_day, c0]
    assert abs(std - mine) < 1e-6, f"自检失败 {c0}@{chk_day.date()}: std {std} mine {mine}"
    print(f"自检通过：{c0}@{chk_day.date()} 向量化 {mine:+.4f} == 标准 {std:+.4f}")

    segs = {"full": R, "IS": R[R.index < pd.Timestamp(SPLIT)],
            "OOS": R[R.index >= pd.Timestamp(SPLIT) + GAP]}
    parts = {k: pd.DataFrame({
        "RankIC": v.mean(), "ICIR": v.mean() / (v.std() + 1e-12),
        "days": v.notna().sum()}) for k, v in segs.items()}
    board = pd.concat(parts, axis=1)
    board.columns = [f"{s}_{c}" for s, c in board.columns]
    board = board[board["full_days"] >= 30]
    # 按 IS 排序（决策视角无未来函数），OOS 列仅存档、验收另看
    board = board.sort_values("IS_ICIR", key=abs, ascending=False)
    board.insert(0, "方向", np.sign(board["IS_RankIC"]).astype(int))
    board.to_csv(derived_dir() / "alpha_board.csv")

    print(f"\n有效基线因子 {len(board)} 个（≥30 采样日），榜按 |IS ICIR| 排序")
    show = ["方向", "full_RankIC", "full_ICIR", "IS_ICIR", "OOS_ICIR",
            "full_days"]
    print("\n=== Top 12（IS 视角）===")
    print(board[show].head(12).round(3).to_string())
    print("\n=== 自家因子同口径对标（同一把尺子：5 日采样 + fwd_ret_5）===")
    print(board.loc[board.index.isin(OWN), show].round(3).to_string())
    same = (np.sign(board["IS_RankIC"]) == np.sign(board["OOS_RankIC"])).mean()
    print(f"\nIS 与 OOS 方向同号率：{same:.0%}（全 {len(board)} 因子，"
          f"衡量榜单时间稳定性）")


if __name__ == "__main__":
    main()
