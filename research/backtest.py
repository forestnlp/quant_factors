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
from research.eval import SPLIT      # IS/OOS 切点与 eval 统一

REBAL_DAYS = 5      # 调仓周期（交易日），与 fwd_ret_5 视野一致
FEE = 0.0013        # 双边近似：佣金万2.5×2 + 卖出印花税 0.05%（2023-08 后）+ 滑点万5


def load_pivots(with_industry: bool = False
                ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """返回 (后复权价 pivot, 可交易布尔 pivot, 特征长表)。

    净值用后复权 post_close（收益率口径与 fwd_ret_5 一致，分红除息不失真）；
    可交易性判断用真实价 close vs high_limit（涨跌停仅此口径有意义）。
    with_industry=True 时特征长表附加 sw_l1（季末快照 as-of，与 eval 同语义）。
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
    if with_industry:
        from research.eval import _asof_industry
        ind = pd.read_parquet(derived_dir() / "industry.parquet")
        ind = ind[["date", "code", "sw_l1"]].rename(columns={"date": "snap"})
        ind["snap"] = pd.to_datetime(ind["snap"])
        f = f.assign(dt=f["date"])       # _asof_industry 以 dt 为键
        f = _asof_industry(f, ind)
    return price, tr, f


FEATURE_COLS: list[str] = []   # main() 里按参数填


def topk_weights(feat: pd.DataFrame, col: str, k: int,
                 tradable: pd.DataFrame, rebal: int,
                 reverse: bool = False, buffer: int = 0,
                 band: tuple[float, float] | None = None,
                 neutral: bool = False, smooth: int = 0) -> pd.DataFrame:
    """每 rebal 交易日在可交易票中重选 Top-K → 目标权重 pivot。

    调仓日：入选票各 1/nsel，其余 0（清出榜）；非调仓日：整行 NaN（不出单）。
    reverse=False 取因子值最小端（负向因子），True 取最大端。

    机制（默认关，全关时等价原始 Top-K 行为）：
        buffer：缓冲带只数——仅对"绝对名次型"信号有意义（band 关闭时）。
        band：名次分位带 (q_lo, q_hi]，只在带内选。
        neutral：分位改在"日×行业"内计算（行业中性选股，剥行业贝塔）。
        smooth：对每日名次分位做逐股滚动均值（span 日），压换手。
    """
    cols = ["date", "code", col] + (["sw_l1"] if neutral else [])
    sub = feat[cols].merge(
        tradable.stack().rename("t").reset_index(), on=["date", "code"])
    sub = sub[sub["t"] & sub[col].notna()]
    grp = ["date"] + (["sw_l1"] if neutral else [])
    rk = sub.groupby(grp)[col].rank(ascending=not reverse, method="first")
    n = sub.groupby(grp)[col].transform("size")
    q = (rk / n).rename("q")
    sel = sub.assign(q=q.values)
    if smooth:
        sel = sel.sort_values(["code", "date"])
        sel["q"] = (sel.groupby("code", sort=False)["q"]
                    .transform(lambda s: s.rolling(
                        smooth, min_periods=max(2, smooth // 3)).mean()))
    dates = sorted(feat["date"].unique())[::rebal]
    sel = sel[sel["date"].isin(dates)].sort_values("q")
    if band is not None:
        sel = sel[(sel["q"] >= band[0]) & (sel["q"] <= band[1])]

    w = pd.DataFrame(np.nan, index=tradable.index, columns=tradable.columns)
    held: set[str] = set()
    for d, g in sel.groupby("date"):
        g = g.sort_values("q")
        # 带内按分位取前 k 为理想持仓、前 k+buffer 为可留存
        keep = [c for c in g["code"].head(k + buffer) if c in held]
        quota = max(k - len(keep), 0)
        new = [c for c in g["code"].head(k) if c not in held][:quota]
        target = keep + new
        held = set(target)
        if not target:
            continue
        w.loc[d, :] = 0.0
        w.loc[d, target] = 1.0 / len(target)
    return w


def run(col: str, k: int, rebal: int, reverse: bool = False,
        fee: float = FEE, buffer: int = 0,
        band: tuple[float, float] | None = None, quiet: bool = False,
        neutral: bool = False, smooth: int = 0) -> dict:
    price, tradable, feat = load_pivots(with_industry=neutral)
    w = topk_weights(feat, col, k, tradable, rebal, reverse=reverse,
                     buffer=buffer, band=band, neutral=neutral, smooth=smooth)
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
    band_s = f"  带[{band[0]:.2f},{band[1]:.2f}]" if band else ""
    extra = ("  行业中性" if neutral else "") + (f"  平滑{smooth}" if smooth else "")
    if not quiet:
        print(f"=== 因子 {col}  Top-{k}  每 {rebal} 日调仓  buffer={buffer}"
              f"{band_s}{extra}  双边费率 {fee:.2%}  做多{'大' if reverse else '小'}端 ===")
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
    # 超额口径（alpha 裁判）：日频对齐后 组合-基准 的差值序列
    idx = ret.index.intersection(r_mkt.index)
    ex = ret.loc[idx] - r_mkt.loc[idx]
    ann_ex = float((1 + ex).prod() ** (252 / len(ex)) - 1)
    te = float(ex.std() * np.sqrt(252))                       # 跟踪误差
    ir = float(ex.mean() / (ex.std() + 1e-12) * np.sqrt(252))  # 信息比率
    beta = float(np.cov(ret.loc[idx], r_mkt.loc[idx])[0, 1] / np.var(r_mkt.loc[idx]))
    corr = float(np.corrcoef(ret.loc[idx], r_mkt.loc[idx])[0, 1])
    if not quiet:
        print(f"  [基准] 全市场等权（后复权） 年化 {float(ann_m):+.1%}"
              f"（策略超额 {float(ann - ann_m):+.1%}）")
        print(f"  [超额] 年化 {ann_ex:+.1%}  跟踪误差 {te:.1%}  IR {ir:.2f}   "
              f"贝塔 {beta:.2f}  相关 {corr:.2f}")
    # IS/OOS 分段：与 eval.py 同切点（IS 调参、OOS 验收只看一次）
    res = {"ann": float(ann), "sharpe": float(shp), "dd": float(dd),
           "fees_pct": fees / 1e8, "n_orders": len(pf.orders),
           "ann_mkt": float(ann_m), "ann_ex": ann_ex, "te": te,
           "ir": ir, "beta": beta, "corr": corr}
    split = pd.Timestamp(SPLIT)
    for seg, r, e in (("IS", ret[ret.index < split], ex[ex.index < split]),
                      ("OOS", ret[ret.index >= split], ex[ex.index >= split])):
        if len(r) < 30:
            continue
        a_ = (1 + r).prod() ** (252 / len(r)) - 1
        s_ = r.mean() / (r.std() + 1e-12) * np.sqrt(252)
        ir_ = float(e.mean() / (e.std() + 1e-12) * np.sqrt(252))
        res[f"{seg}_ann"], res[f"{seg}_sharpe"], res[f"{seg}_ir"] = \
            float(a_), float(s_), ir_
        if not quiet:
            print(f"  [{seg:3s}] {r.index[0].date()}~{r.index[-1].date()} "
                  f"年化 {float(a_):+.1%}  Sharpe {float(s_):.2f}  IR {ir_:.2f}")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Top-K 轮动组合回测")
    ap.add_argument("factor", nargs="?", default="v_amt_5_20")
    ap.add_argument("-k", type=int, default=100)
    ap.add_argument("--rebal", type=int, default=REBAL_DAYS, help="调仓周期（交易日）")
    ap.add_argument("--reverse", action="store_true",
                    help="做多因子值最大端（默认做多最小端）")
    ap.add_argument("--buffer", type=int, default=0,
                    help="缓冲带只数：持仓跌出 k+buffer 才清出（0=关）")
    ap.add_argument("--band", default=None,
                    help="截面名次分位带，如 0.10,0.50（跳过最低10%%）")
    ap.add_argument("--neutral", action="store_true",
                    help="分位在日×行业内计算（行业中性选股）")
    ap.add_argument("--smooth", type=int, default=0,
                    help="名次分位逐股滚动均值天数（压换手，0=关）")
    a = ap.parse_args()
    FEATURE_COLS.append(a.factor)
    bd = tuple(float(x) for x in a.band.split(",")) if a.band else None
    run(a.factor, a.k, a.rebal, a.reverse, buffer=a.buffer, band=bd,
        neutral=a.neutral, smooth=a.smooth)
