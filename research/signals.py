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
    conda run -n jaycode python -m research.signals --col mlb_xgb -k 5 --track \
        --skip-refresh   # 役55 A1 形态（确认跟踪）：ML Top-5 + 两道执行提示
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
# 役55 A1 固定参数（PROJECT.md 结论55 写死）：确认=候选日后 3 日内收盘
# 涨≥1×σ14；追踪线=入场后最高收盘−2.5×当日收盘×当日σ14，跌破即卖。
CONF_WIN, CONF_SIG, TRAIL = 3, 1.0, 2.5


def track_hints(sig_day, hold: list[str]) -> dict:
    """役55 A1 执行提示（无状态纯函数）：对 Top-k 名单逐票给
    确认状态（候选日后 CONF_WIN 日内收盘是否触及 确认线=候选日收盘
    ×(1+CONF_SIG×σ14候选日)）与今日追踪线。确认日=窗口内首个触及日，
    追踪最高价自确认日起算（与 battle_confirm 仿真一致；未确认票追踪线
    给 None，只等确认）。"""
    w = pd.read_parquet(derived_dir() / "features.parquet",
                        columns=["date", "code", "r_1", "post_close"])
    w = w[w["code"].isin(hold)]
    w["date"] = pd.to_datetime(w["date"])
    c = w.pivot(index="date", columns="code", values="post_close")
    s = w.pivot(index="date", columns="code", values="r_1") \
         .rolling(14, min_periods=10).std()
    out = {}
    for code in hold:
        if code not in c.columns:
            continue
        cc, ss = c[code], s[code]
        ref, sig0 = cc.get(sig_day), ss.get(sig_day)
        if pd.isna(ref) or pd.isna(sig0):
            continue
        confirm_line = ref * (1 + CONF_SIG * sig0)
        win = cc.loc[sig_day:].iloc[1:CONF_WIN + 1]      # 候选日后 3 个交易日
        hit = win[win >= confirm_line]
        conf_day = hit.index.min() if len(hit) else None
        hint = {"confirmed": conf_day is not None,
                "confirm_line": round(float(confirm_line), 2)}
        if conf_day is None:
            # 窗口是否已走完：走完仍未确认 = 本局作废（与仿真 dl 过期一致）
            hint["window_over"] = bool(len(cc.loc[sig_day:]) > CONF_WIN)
        if conf_day is not None:
            since = cc.loc[conf_day:]
            runhigh = float(since.max())
            last = float(cc.iloc[-1])
            last_s = float(ss.dropna().iloc[-1])   # σ 尾窗 NaN 时退用最近值
            trail_line = runhigh - TRAIL * last * float(last_s)
            hint.update(
                entry=str(conf_day.date()),
                runhigh=round(runhigh, 2),
                trail_line=round(trail_line, 2),
                sell_now=bool(last < trail_line))
        out[code] = hint
    return out


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
          band: tuple[float, float], skip_refresh: bool = False,
          track: bool = False) -> dict:
    if not skip_refresh:
        _refresh_alpha(col)              # 产物滞后宽表 → 先重编译（防旧因子出旧单）
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
    r = {
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
    if track:
        r["track"] = track_hints(sig_day, held)   # 役55 A1 确认/追踪提示
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description="每日荐股（复用回测选股实现）")
    ap.add_argument("--col", default=DEFAULT["col"])
    ap.add_argument("-k", type=int, default=DEFAULT["k"])
    ap.add_argument("--rebal", type=int, default=DEFAULT["rebal"])
    ap.add_argument("--no-reverse", action="store_true",
                    help="因子高值端为差（默认做多高值端）")
    ap.add_argument("--track", action="store_true",
                    help="役55 A1：输出确认闸门+追踪线两道执行提示")
    ap.add_argument("--skip-refresh", action="store_true",
                    help="跳过 alpha 产物重编译（ML 合成信号无表达式时用）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    r = build(a.col, a.k, a.rebal, not a.no_reverse, DEFAULT["band"],
              skip_refresh=a.skip_refresh, track=a.track)
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
    if "track" in r:
        print(f"【役55 执行提示】确认线=候选日收盘×(1+1×σ14)（{CONF_WIN} 日内"
              f"须触及才建仓）；追踪线=确认后最高收盘−{TRAIL}×当日波动（跌破即卖）")
        for h in r["hold"]:
            c = h["code"]
            t = r["track"].get(c)
            if t is None:
                continue
            if t["confirmed"]:
                flag = "⚠️ 跌破追踪线→卖出" if t["sell_now"] else "持有"
                print(f"  {c} 已确认({t['entry']}) 追踪线 {t['trail_line']}"
                      f"（最高 {t['runhigh']}）→ {flag}")
            else:
                print(f"  {c} 未确认 确认线 {t['confirm_line']} → 暂不建仓，等下局")
    print(f"[存] {p}")


if __name__ == "__main__":
    main()
