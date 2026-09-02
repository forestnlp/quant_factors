# -*- coding: utf-8 -*-
"""数据体检：raw 层完整性 / 日历对齐 / 跨数据集一致性

每次增量取数后跑一次，作为数据入库的验收门（rules.md 教训 1/4）。
全部只读 data/raw/，不写任何文件。

用法：
    conda run -n jaycode python -m research.check
"""

from __future__ import annotations

import glob
import os

import pandas as pd

from research.config import raw_dir

SINCE = "2025-01-04"      # 当前 raw 层的检查起点（与各数据集取数起点一致）


def _load(name: str, cols: list[str] | None = None) -> pd.DataFrame:
    files = sorted(glob.glob(str(raw_dir("jq", name) / "*.csv")))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_csv(f, usecols=cols) for f in files],
                     ignore_index=True)


def _calendar() -> list[str]:
    p = raw_dir("jq") / "trading_calendar.csv"
    return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip()]


def _col_date(df: pd.DataFrame) -> str:
    for c in ("time", "day", "date"):
        if c in df.columns:
            return c
    raise KeyError("找不到日期列")


def main() -> None:
    cal = set(_calendar())
    print("=" * 62)
    print("一、基础盘面")
    daily = _load("daily")
    dcol = _col_date(daily)
    days_all = sorted(daily[dcol].unique())
    exp = [d for d in sorted(cal) if SINCE <= d <= days_all[-1]]
    print(f"日线: {len(daily)} 行, {days_all[0]} ~ {days_all[-1]}"
          f"（{len(days_all)} 个交易日）")

    print("\n二、日历对齐（有没有跑漏）")
    miss_days = sorted(set(exp) - set(days_all))
    not_in_cal = sorted(set(days_all) - cal)
    print(f"期望交易日 {len(exp)} 天; 日线缺日 {len(miss_days)} 天"
          f"{' 缺: ' + ','.join(miss_days[:10]) if miss_days else ' ✓'}")
    print(f"日历外野日期 {len(not_in_cal)} 天"
          f"{' 野: ' + ','.join(not_in_cal[:10]) if not_in_cal else ' ✓'}")
    cnt = daily.groupby(dcol).size()
    thin = cnt[cnt < 4500]
    print(f"单日标的数过少(<4500): {len(thin)} 天"
          f"{' 例如: ' + str(thin.head(3).to_dict()) if len(thin) else ' ✓'}")

    print("\n三、日线内部质量")
    nan_close = daily[daily["close"].isna()]
    print(f"close 为 NaN: {len(nan_close)} 行"
          f"（其中 paused=1 有 {int((nan_close['paused'] == 1).sum())} 行，"
          f"paused 也为 NaN 有 {int(nan_close['paused'].isna().sum())} 行）")
    if len(nan_close):
        nc = daily.loc[nan_close.index].groupby("code").size().sort_values(ascending=False)
        print(f"  NaN 集中前 3 只: {nc.head(3).to_dict()}"
              "（预期：长期停牌股 / 当日新上市无成交）")
    dup = daily.duplicated(subset=[dcol, "code"]).sum()
    print(f"重复 (日,码): {dup}" + (" ✓" if dup == 0 else " ！需去重"))
    # 复权连续性 sanity：|后复权日收益 - 真实价日收益| 应很小（除权日除外）
    s = daily[daily["code"] == "600519.XSHG"].sort_values(dcol)
    r_raw = s["close"].pct_change()
    r_post = s["post_close"].pct_change()
    gap = (r_raw - r_post).abs()
    print(f"茅台 真实价/后复权 日收益差>1%%的天数: {int((gap > 0.01).sum())}"
          "（应为 0 或仅除权日）")

    print("\n四、跨数据集对齐（以日线 (日,码) 为主键）")
    key = daily[[dcol, "code"]].rename(columns={dcol: "d"})
    for name, datecol, codecol, probe in [
            ("valuation", "day", "code", "pe_ratio"),
            ("money_flow", "date", "sec_code", "net_amount_main")]:
        df = _load(name)
        if df.empty:
            print(f"{name}: 无数据 ！")
            continue
        df = df.drop_duplicates(subset=[datecol, codecol])
        df = df[df[datecol] <= days_all[-1]]
        n_dup_raw = 0  # 重叠片在 drop_duplicates 前统计
        m = key.merge(df[[datecol, codecol, probe]].rename(
            columns={datecol: "d", codecol: "code"}), on=["d", "code"], how="left")
        rate = m[probe].notna().mean()
        d_set = set(df[datecol])
        miss = sorted(set(exp) - d_set)
        print(f"{name}: {len(df)} 行(去重), 日期 {df[datecol].nunique()} 天"
              f"{' 缺日 ' + str(len(miss)) if miss else ' ✓'}, "
              f"主键匹配率 {rate:.4f}" + (" ✓" if rate > 0.95 else " ！"))

    # 语义一致性：money_flow.change_pct vs 日线真实价涨幅
    mf = _load("money_flow", ["date", "sec_code", "change_pct"])
    mf = mf.drop_duplicates(subset=["date", "sec_code"])
    d2 = daily[[dcol, "code", "close"]].copy()
    d2["pre_close"] = d2.groupby("code")["close"].shift(1)
    d2["ret"] = (d2["close"] / d2["pre_close"] - 1) * 100
    j = mf.merge(d2.rename(columns={dcol: "date", "code": "sec_code"}),
                 on=["date", "sec_code"], how="inner")
    diff = (j["change_pct"] - j["ret"]).abs()
    ok = (diff <= 0.11).mean()   # 0.11 个百分点以内视为一致（四舍五入差）
    print(f"语义校验 change_pct vs 日线涨幅: 一致率 {ok:.4f}"
          + (" ✓" if ok > 0.99 else " ！"))

    print("\n五、行业 PIT 快照")
    ind = _load("industry")
    if not ind.empty:
        for d, g in ind.groupby("day"):
            print(f"  {d}: {len(g)} 只, sw_l1 覆盖 {g['sw_l1'].astype(bool).mean():.3f}")
    print("=" * 62)
    print("六、数据清单（当前 raw 层拥有的一切）")
    for name in ["daily", "valuation", "money_flow", "industry", "auction"]:
        files = sorted(glob.glob(str(raw_dir("jq", name) / "*.csv")))
        if not files:
            print(f"  {name:12s}: 未取数")
            continue
        size = sum(os.path.getsize(f) for f in files) / 2**20
        df = _load(name)
        rng = f"{df[_col_date(df)].min()} ~ {df[_col_date(df)].max()}"
        print(f"  {name:12s}: {len(files)} 片, {len(df)} 行, {size:.0f}MB, {rng}")


def _limit_bound(code: str) -> float:
    """按板块推断涨跌幅限制（第三只眼：用交易所规则拷问数据）。"""
    if code.startswith(("688", "300", "301")):
        return 0.20                      # 科创板 / 创业板
    if code.startswith(("83", "87", "43", "92")):
        return 0.30                      # 北交所
    return 0.10                          # 主板


def deep_rules() -> None:
    """七、交易规则对抗审计：数据必须满足的外部常识。"""
    daily = _load("daily")
    dcol = _col_date(daily)
    df = daily.dropna(subset=["close", "low", "high", "open"]).copy()
    df = df.sort_values(["code", dcol])
    df["pre_close"] = df.groupby("code")["close"].shift(1)
    df["seq"] = df.groupby("code").cumcount()
    ok = df[(df["pre_close"].notna()) & (df["seq"] >= 6)]
    # 除权除息日 pre_close 会变，涨跌幅比例失真 → 容忍小比例违例并看分布
    band_bad = ok[(ok["open"] < ok["low"]) | (ok["open"] > ok["high"])
                  | (ok["close"] < ok["low"]) | (ok["close"] > ok["high"])]
    print(f"\n七、交易规则对抗审计")
    print(f"价格带违例(开/收越出[低,高]): {len(band_bad)} 行 / {len(ok)}"
          + (" ✓" if len(band_bad) == 0 else f" 例:\n{band_bad.head(3).to_string()}"))
    # 交易所口径：涨停价 = round(除权后基准价 × (1+限幅), 0.01)。
    # 除权后基准价由 post/raw 比价跳变系数 k 反推（非除权日 k=1，自动统一）。
    ok["ratio"] = ok["high_limit"] / ok["pre_close"]
    bound = ok["code"].map(_limit_bound)
    ok["dr"] = ok["post_close"] / ok["close"]
    k = (ok.groupby("code")["dr"].pct_change() + 1).clip(lower=1.0).fillna(1.0)
    pre_adj = ok["pre_close"] / k
    hl_full = (pre_adj * (1 + bound)).round(2)
    hl_half = (pre_adj * (1 + bound / 2)).round(2)          # ST 半额
    tick = 0.011                                             # 一个报价档位
    list_day = ok.groupby("code")["time"].transform("min")
    age = (pd.to_datetime(ok["time"]) - pd.to_datetime(list_day)).dt.days
    viol = ((abs(ok["high_limit"] - hl_full) > tick)
            & (abs(ok["high_limit"] - hl_half) > tick)
            & (age > 30) & (ok["volume"] > 0))               # 次新期/停牌冻结豁免
    print(f"涨停价规则违例(交易所口径,除权/次新/停牌豁免后): {int(viol.sum())} 行"
          f" ({viol.mean():.5%})" + (" ✓" if viol.mean() < 0.0005 else " ！"))
    if viol.any():
        vv = ok[viol]
        print("  样例:\n" + vv[["time", "code", "pre_close", "high_limit", "ratio"]]
              .head(5).to_string(index=False))
    mv = ok[(ok["volume"] > 0) & ok["money"].notna()]
    mv_bad = mv[(mv["money"] < mv["volume"] * mv["low"] * 0.98)
                | (mv["money"] > mv["volume"] * mv["high"] * 1.02)]
    print(f"额量价一致性违例(money 越出 vol×[low,high]±2%): {len(mv_bad)}"
          + (" ✓" if len(mv_bad) == 0 else " ！"))

    mf = _load("money_flow")
    mf = mf.drop_duplicates(subset=["date", "sec_code"])
    bal = mf.dropna(subset=["net_amount_main", "net_amount_xl", "net_amount_l"])
    resid = (bal["net_amount_main"]
             - bal["net_amount_xl"] - bal["net_amount_l"]).abs()
    scale = bal["net_amount_main"].abs().clip(lower=1.0)
    bad_bal = (resid / scale > 0.05).sum()
    print(f"资金流守恒违例(主力 != 超大+大, 相对>5%): {int(bad_bal)} / {len(bal)}"
          + (" ✓" if bad_bal / max(len(bal), 1) < 0.01 else " ！"))

    v = _load("valuation").drop_duplicates(subset=["day", "code"])
    v = v.dropna(subset=["market_cap", "pb_ratio"])
    neg_mc = int((v["market_cap"] <= 0).sum())
    circ_gt = int((v["circulating_market_cap"] > v["market_cap"] * 1.001).sum())
    pb_neg = int((v["pb_ratio"] < 0).sum())
    print(f"估值合理性: 市值<=0 {neg_mc} 行 ✓, 流通>总市值 {circ_gt} 行"
          + (" ✓" if circ_gt == 0 else " ！") + f", pb<0 {pb_neg} 行"
          + ("（负净资产，可接受）" if pb_neg else ""))

    ind = _load("industry")
    if not ind.empty:
        snap = ind["day"].max()
        di = set(daily.loc[daily[dcol] == min(
            d for d in daily[dcol].unique() if d >= snap), "code"])
        ii = set(ind.loc[ind["day"] == snap, "code"])
        print(f"行业快照({snap}) vs 日线标的: 交集 {len(ii & di)},"
              f" 行业独有 {len(ii - di)}(退市/停牌当日不在日线, 正常),"
              f" 日线独有 {len(di - ii)}(快照日之后上市)")


if __name__ == "__main__":
    main()
