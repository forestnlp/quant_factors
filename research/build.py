# -*- coding: utf-8 -*-
"""L2 特征层：raw CSV → 派生宽表 + 维表（幂等，可从 raw 完整重建）

输出（data/derived/，全部 parquet）：
    features.parquet  数值宽表：(date, code) × 特征 + 前瞻标签 fwd_ret_5
    industry.parquet  行业维表（季末快照，评估端按日 as-of join）
    concept.parquet   概念长表（季末快照原样）：(date, concept, concept_name, code)
    finance.parquet   财务公告合并（pub_date 与报告期分存，L3 按公告日 as-of）

PIT 纪律：特征只用 T 日及以前的数据；T 日估值 NaN 不填充；
标签 fwd_ret_5 用后复权价 T+5 收盘（评估时自然形成 5 天空隙）。

用法：conda run -n jaycode python -m research.build
"""

from __future__ import annotations

import glob

import numpy as np
import pandas as pd

from research.config import raw_dir, derived_dir


def _load_raw(name: str) -> pd.DataFrame:
    files = sorted(glob.glob(str(raw_dir("jq", name) / "*.csv")))
    if not files:
        raise FileNotFoundError(f"raw/{name} 无数据，先跑 fetch {name}")
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def build_features() -> pd.DataFrame:
    """数值特征宽表。列名规范：r_ 收益动量 / v_ 量能波动 / vlm 估值 / mf 资金流。"""
    d = _load_raw("daily").drop_duplicates(subset=["time", "code"])
    d = d.rename(columns={"time": "date"}).sort_values(["code", "date"])
    d = d.reset_index(drop=True)   # 固定索引，merge 前后 g 结果均对齐
    g = d.groupby("code", sort=False)

    # fill_method=None：停牌 NaN 不得前向填充，否则算出虚假收益
    d["r_1"] = g["post_close"].pct_change(fill_method=None)
    for n in (5, 10, 20, 60):
        d[f"r_{n}d"] = g["post_close"].transform(
            lambda s, n=n: s / s.shift(n) - 1)
    # 标签：T+5 后复权收益（评估端负责切分与空隙，这里只算全表；须在 merge 前）
    d["fwd_ret_5"] = g["post_close"].transform(lambda s: s.shift(-5) / s - 1)
    d["v_std_20"] = g["r_1"].transform(lambda s: s.rolling(20).std())
    d["v_amt_5_20"] = (g["money"].transform(lambda s: s.rolling(5).mean())
                       / g["money"].transform(lambda s: s.rolling(20).mean()))
    vwap = d["money"] / d["volume"].replace(0, np.nan)
    d["v_vwap_dev"] = d["close"] / vwap - 1
    rng = (d["high"] - d["low"]).replace(0, np.nan)
    d["v_close_loc"] = (d["close"] - d["low"]) / rng

    # 按股滚动相关（money 与 close），用滚动矩手工算，保证索引对齐
    d["_mxc"] = d["money"] * d["close"]
    _mx = g["money"].transform(lambda s: s.rolling(20).mean())
    _cx = g["close"].transform(lambda s: s.rolling(20).mean())
    _mxc = g["_mxc"].transform(lambda s: s.rolling(20).mean())
    _sx = g["money"].transform(lambda s: s.rolling(20).std())
    _sc = g["close"].transform(lambda s: s.rolling(20).std())
    d["v_corr_pv_20"] = (_mxc - _mx * _cx) / (_sx * _sc)
    d = d.drop(columns=["_mxc"])

    # 估值：T 日行聚宽本就给 NaN（盘前不可得），join 后保留 NaN、不填充
    v = _load_raw("valuation").drop_duplicates(subset=["day", "code"])
    v = v.rename(columns={"day": "date"})
    d = d.merge(v[["date", "code", "pe_ratio", "pb_ratio",
                   "market_cap", "circulating_market_cap"]],
                on=["date", "code"], how="left")
    d["vlm_ln_mv"] = np.log(d["market_cap"].where(d["market_cap"] > 0))
    d["vlm_ln_circ"] = np.log(
        d["circulating_market_cap"].where(d["circulating_market_cap"] > 0))
    d["vlm_turnover"] = d["money"] / (d["market_cap"] * 1e8)  # 成交额/总市值

    mf = _load_raw("money_flow").drop_duplicates(subset=["date", "sec_code"])
    mf = mf.rename(columns={"sec_code": "code",
                            "net_pct_main": "mf_net_pct_main",
                            "net_pct_l": "mf_net_pct_l"})
    d = d.merge(mf[["date", "code", "mf_net_pct_main", "mf_net_pct_l"]],
                on=["date", "code"], how="left")

    # 竞价（9:25 即知，当日可用）：额、相对买卖失衡、额占全日比须 build 端算
    au = _load_raw("auction").drop_duplicates(subset=["day", "code"])
    au = au.rename(columns={"day": "date", "current": "auc_price",
                            "money": "auc_money", "b1_v": "auc_b1",
                            "a1_v": "auc_a1"})
    d = d.merge(au[["date", "code", "auc_money", "auc_b1", "auc_a1"]],
                on=["date", "code"], how="left")
    imb_den = (d["auc_b1"] + d["auc_a1"]).replace(0, np.nan)
    d["auc_imb"] = (d["auc_b1"] - d["auc_a1"]) / imb_den      # 竞价买卖失衡
    d["auc_money_share"] = d["auc_money"] / d["money"]         # 竞价额占全日比

    # 两融（T+1 晨间才公布 T 日余额 → 一律滞后一日使用，防未来函数）
    mt = _load_raw("mtss").drop_duplicates(subset=["date", "sec_code"])
    mt = mt.rename(columns={"sec_code": "code",
                            "fin_value": "mt_fin_value",
                            "sec_value": "mt_sec_value"})
    mt["mt_date"] = pd.to_datetime(mt["date"]) + pd.Timedelta(days=1)
    d["date_dt"] = pd.to_datetime(d["date"])
    d = pd.merge_asof(
        d.sort_values("date_dt").reset_index(drop=True),
        mt[["code", "mt_date", "mt_fin_value", "mt_sec_value"]]
        .sort_values("mt_date"),
        left_on="date_dt", right_on="mt_date", by="code",
        direction="backward", tolerance=pd.Timedelta(days=7))
    # 融资余额/总市值（市值单位亿元→元）；非两融标的为 NaN 属正常
    d["mt_fin_ratio"] = d["mt_fin_value"] / (d["market_cap"] * 1e8)

    # 龙虎榜（T 日盘后公布 → 仅 T+1 单日可用）：等值 join 生效日即可
    bb = _load_raw("billboard")[["day", "code"]].drop_duplicates()
    bb["bb_date"] = pd.to_datetime(bb["day"]) + pd.Timedelta(days=1)
    bb["bb_yest"] = 1.0
    d = d.merge(bb[["bb_date", "code", "bb_yest"]].rename(
        columns={"bb_date": "date_dt"}), on=["date_dt", "code"], how="left")
    d["bb_yest"] = d["bb_yest"].fillna(0.0)

    # ST（盘前已知，当日可用）
    st = _load_raw("st")[["day", "code"]].drop_duplicates()
    st["st_flag"] = 1.0
    d = d.merge(st.rename(columns={"day": "date"}), on=["date", "code"],
                how="left")
    d["st_flag"] = d["st_flag"].fillna(0.0)

    keep = ["date", "code", "close", "paused", "high_limit", "low_limit",
            "st_flag",
            "r_1", "r_5d", "r_10d", "r_20d", "r_60d",
            "v_std_20", "v_amt_5_20", "v_vwap_dev", "v_close_loc",
            "v_corr_pv_20",
            "pe_ratio", "pb_ratio", "vlm_ln_mv", "vlm_ln_circ", "vlm_turnover",
            "mf_net_pct_main", "mf_net_pct_l",
            "auc_imb", "auc_money_share", "mt_fin_ratio", "bb_yest",
            "fwd_ret_5"]
    feat = d[keep].copy()
    feat.to_parquet(derived_dir() / "features.parquet", index=False)
    return feat


def build_dims() -> None:
    """行业/概念/财务维表（快照形态，as-of 语义由评估端实现，此处不改数据）。"""
    ind = _load_raw("industry").drop_duplicates(subset=["day", "code"])
    ind = ind.rename(columns={"day": "date"}).sort_values(["code", "date"])
    ind.to_parquet(derived_dir() / "industry.parquet", index=False)

    con = _load_raw("concept").drop_duplicates(subset=["day", "concept", "code"])
    con = con.rename(columns={"day": "date"}).sort_values(["date", "concept"])
    con.to_parquet(derived_dir() / "concept.parquet", index=False)

    fin = _load_raw("finance").drop_duplicates(subset=["code", "end_date"])
    fin = fin.sort_values(["code", "end_date"])
    fin.to_parquet(derived_dir() / "finance.parquet", index=False)


def main() -> None:
    derived_dir().mkdir(parents=True, exist_ok=True)
    feat = build_features()
    build_dims()
    dt = feat["date"]
    print("features.parquet: %d 行, %d 天 (%s ~ %s), %d 只"
          % (len(feat), dt.nunique(), dt.min(), dt.max(),
             feat["code"].nunique()))
    nan = feat[[c for c in feat.columns if c not in ("date", "code")]].isna().mean()
    print("NaN 率>50%% 的列: %s" % nan[nan > 0.5].round(3).to_dict())
    for nm in ("industry", "concept", "finance"):
        df = pd.read_parquet(derived_dir() / f"{nm}.parquet")
        print(f"{nm}.parquet: {len(df)} 行")
    ok = feat["fwd_ret_5"].notna() & feat["r_20d"].notna()
    print("可用样本(r_20d 与标签同时非空): %d" % int(ok.sum()))


if __name__ == "__main__":
    main()
