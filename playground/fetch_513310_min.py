# -*- coding: utf-8 -*-
"""抓取中韩半导体ETF(513310) 5分钟K线并本地化存储（实验区）

数据源：东方财富 kline 接口（push2his.eastmoney.com）
输出：data/bt_export/513310_5min.csv（仅保留已收盘的完整交易日，每日48根bar）

用法：
    conda run -n jaycode python playground/fetch_513310_min.py

成功标准：
    脚本无异常退出，生成 CSV，打印有效交易日数与区间。
"""

import time
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SECID = "1.513310"
PERIOD = "5"
OUT = PROJECT_ROOT / "data" / "bt_export" / "513310_5min.csv"


def fetch_kline(retries: int = 4) -> pd.DataFrame:
    """请求东方财富 kline 接口，返回原始 DataFrame。"""
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "klt": PERIOD,
        "fqt": "0",
        "secid": SECID,
        "beg": "20230101",
        "end": "20500000",
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=20, params=params, headers=headers)
            data_json = r.json()
            if not data_json.get("data") or not data_json["data"].get("klines"):
                raise ValueError(f"无数据: {data_json}")
            rows = [item.split(",") for item in data_json["data"]["klines"]]
            return pd.DataFrame(
                rows,
                columns=["时间", "开盘", "收盘", "最高", "最低", "成交量", "成交额",
                         "振幅", "涨跌幅", "涨跌额", "换手率"],
            )
        except Exception as e:  # noqa: BLE001
            print(f"  第{attempt+1}次尝试失败: {e}")
            time.sleep(2 * (attempt + 1))
    raise SystemExit("多次请求均失败。")


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """清洗：转类型、只保留已收盘完整交易日（每日48根bar）。"""
    df = df.copy()
    for c in ["开盘", "收盘", "最高", "最低", "成交量", "成交额"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["时间"] = pd.to_datetime(df["时间"])
    df["date"] = df["时间"].dt.date

    # 剔除未收盘的不完整日（bar数 < 40，完整日为48）
    cnt = df.groupby("date")["时间"].transform("count")
    df = df[cnt >= 40].copy()

    return df[["date", "时间", "开盘", "收盘", "最高", "最低", "成交量", "成交额"]]


def main() -> None:
    # 优先使用本地已抓取的原始数据，避免被东财限流；否则联网拉取
    raw_csv = PROJECT_ROOT / "data" / "bt_export" / "513310_5min_raw.csv"
    if raw_csv.exists():
        print(f"使用本地原始数据: {raw_csv}")
        raw = pd.read_csv(raw_csv)
    else:
        print("本地无原始数据，联网拉取 ...")
        raw = fetch_kline()

    df = clean(raw)
    df = df.sort_values("时间").reset_index(drop=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)

    n_days = df["date"].nunique()
    print(f"有效交易日: {n_days}，区间 {df['date'].min()} ~ {df['date'].max()}")
    print(f"总bar数: {len(df)}，每日bar数示例: {df.groupby('date').size().iloc[0]}")
    print(f"已保存 -> {OUT}")


if __name__ == "__main__":
    main()
