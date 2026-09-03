# -*- coding: utf-8 -*-
"""L3 第二仗：组合级回测（vectorbt，Top-K 轮动 + 真实费率）

与 eval.py 的分工：eval 看"因子有没有信号"（IC/分层），本脚本看"信号能不能变成钱"：
Top-K 等权持仓、5 日调仓、双边费率+印花税近似、只做多、只在可交易票里选。

实现方式：vectorbt Portfolio.from_orders（单组合、cash_sharing=True）——
    调仓日整行给出目标权重（入选 1/K，其余 0 → 强制清出榜票），
    非调仓日为 NaN（不出单，权重自由漂移）——严格 5 日轮动语义。
    近似：调仓日对停牌/触板票的卖出单按理论价成交（未建模卖不掉）。
价格用后复权 post_close（收益率口径与 fwd_ret_5 一致，分红除息不失真）。

用法：
    conda run -n jaycode python -m research.backtest v_amt_5_20 -k 100
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import vectorbt as vbt

from research.config import derived_dir

REBAL_DAYS = 5      # 调仓周期（交易日），与 fwd_ret_5 视野一致
FEE = 0.0013        # 双边近似：佣金万2.5×2 + 卖出印花税 0.05%（2023-08 后）+ 滑点万5


def load_pivots() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """返回 (后复权价 pivot, 可交易布尔 pivot, 特征长表)。

    净值用后复权 post_close（收益率口径与 fwd_ret_5 一致，分红除息不失真）；
    可交易性判断用真实价 close vs high_limit（涨跌停仅此口径有意义）。
    """
    f = pd.read_parquet(
        derived_dir() / "features.parquet",
        columns=["date", "code", "close", "post_close", "paused", "st_flag",
                 "high_limit"] + FEATURE_COLS)
    f["date"] = pd.to_datetime(f["date"])   # 统一 datetime 轴（宽表里 date 是 str）
    price = f.pivot(index="date", columns="code", values="post_close")
    price = price.ffill().bfill()   # 停牌空窗沿用上收盘价（持仓净值连续），可交易性另由 tradable 控制
    tradable = ((f["paused"].fillna(1) == 0) & (f["st_flag"] == 0)
                & ((f["high_limit"] >= 9000) & (f["high_limit"] != 10000)  # 10000=退市整理哨兵
                   | (f["close"] < f["high_limit"] - 1e-6)).fillna(False))
    tr = f.assign(t=tradable).pivot(index="date", columns="code", values="t")
    tr = tr.fillna(False).astype(bool)   # pivot 空格会带出 NaN → 列变 object → numba 崩
    return price, tr, f


FEATURE_COLS: list[str] = []   # main() 里按参数填


def topk_weights(feat: pd.DataFrame, col: str, k: int,
                 tradable: pd.DataFrame, rebal: int,
                 reverse: bool = False) -> pd.DataFrame:
    """每 rebal 交易日在可交易票中重选 Top-K → 目标权重 pivot。

    调仓日：入选票各 1/nsel，其余 0（清出榜）；非调仓日：整行 NaN（不出单）。
    reverse=False 取因子值最小端（负向因子），True 取最大端。
    """
    sub = feat[["date", "code", col]].merge(
        tradable.stack().rename("t").reset_index(), on=["date", "code"])
    sub = sub[sub["t"] & sub[col].notna()]
    dates = sorted(feat["date"].unique())[::rebal]
    sel = sub[sub["date"].isin(dates)]
    rk = sel.groupby("date")[col].rank(ascending=not reverse, method="first")
    n_sel = sel.groupby("date")[col].transform("size")
    sel = sel[rk <= np.minimum(k, n_sel)]
    w = pd.DataFrame(np.nan, index=tradable.index, columns=tradable.columns)
    for d, grp in sel.groupby("date"):
        w.loc[d, :] = 0.0
        w.loc[d, grp["code"].values] = 1.0 / len(grp)
    return w


def run(col: str, k: int, rebal: int, reverse: bool = False,
        fee: float = FEE) -> None:
    price, tradable, feat = load_pivots()
    w = topk_weights(feat, col, k, tradable, rebal, reverse=reverse)
    pf = vbt.Portfolio.from_orders(
        price, size=w, size_type="targetpercent", cash_sharing=True,
        fees=fee, freq="1D", init_cash=1e8, call_seq="auto")
    pv = pf.value()          # cash_sharing=True → 单列净值
    if isinstance(pv, pd.DataFrame):
        pv = pv.iloc[:, 0]
    pv = pv.astype("float64") / 1e8
    ret = pv.pct_change().dropna()
    ann = (1 + ret).prod() ** (252 / len(ret)) - 1
    shp = ret.mean() / (ret.std() + 1e-12) * np.sqrt(252)
    dd = (pv / pv.cummax() - 1).min()
    fees = float(pf.orders.fees.sum())   # 单组合下用属性访问（单列索引有歧义）
    print(f"=== 因子 {col}  Top-{k}  每 {rebal} 日调仓  双边费率 {FEE:.2%}"
          f"  做多{'大' if reverse else '小'}端 ===")
    print(f"  区间 {pv.index[0].date()} ~ {pv.index[-1].date()}（{len(ret)} 交易日）")
    print(f"  累计 {float(pv.iloc[-1] - 1):+.1%}   年化 {float(ann):+.1%}   "
          f"Sharpe {float(shp):.2f}   最大回撤 {float(dd):.1%}   "
          f"Calmar {float(-ann / dd) if dd else float('nan'):.2f}")
    print(f"  成交 {len(pf.orders)} 笔   总费用 {fees / 1e8:.1%}（占初始资金）   "
          f"日均持仓 {(pf.asset_value(group_by=False) > 1).sum(axis=1).mean():.0f} 只")
    # 基准：全上市票等权（后复权，含停牌日 0 收益）。
    # 注意不可用 r.where(tradable)：ffill 后停牌复牌日的多日累计跳空
    # 全部记入复牌首日，会把"tradable 子集"的日均收益系统性压低（实测 -22.7% vs +10%）。
    r_mkt = price.pct_change().mean(axis=1).dropna()
    ann_m = (1 + r_mkt).prod() ** (252 / len(r_mkt)) - 1
    print(f"  [基准] 全市场等权（后复权） 年化 {float(ann_m):+.1%}"
          f"（策略超额 {float(ann - ann_m):+.1%}）")
    # IS/OOS 分段（时间轴对半切）
    mid = ret.index[len(ret) // 2]
    for seg, r in (("IS ", ret[ret.index < mid]), ("OOS", ret[ret.index >= mid])):
        a_ = (1 + r).prod() ** (252 / len(r)) - 1
        s_ = r.mean() / (r.std() + 1e-12) * np.sqrt(252)
        print(f"  [{seg}] {r.index[0].date()}~{r.index[-1].date()} "
              f"年化 {float(a_):+.1%}  Sharpe {float(s_):.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Top-K 轮动组合回测")
    ap.add_argument("factor", nargs="?", default="v_amt_5_20")
    ap.add_argument("-k", type=int, default=100)
    ap.add_argument("--rebal", type=int, default=REBAL_DAYS, help="调仓周期（交易日）")
    ap.add_argument("--reverse", action="store_true",
                    help="做多因子值最大端（默认做多最小端）")
    a = ap.parse_args()
    FEATURE_COLS.append(a.factor)
    run(a.factor, a.k, a.rebal, a.reverse)
