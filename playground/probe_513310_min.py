# -*- coding: utf-8 -*-
"""探查 513310 的 5 分钟数据可得性（实验区）— 直接请求东财接口

akshare 封装偶发 RemoteDisconnected，此处用原生 requests + 重试直连，
确认能否拿到 5 分钟历史 K 线及其覆盖范围。

用法：
    conda run -n jaycode python playground/probe_513310_min.py
"""

import time
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def fetch_kline(period: str = "5", retries: int = 4) -> pd.DataFrame:
    """请求东方财富 kline 接口，返回解析后的 DataFrame。"""
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "klt": period,
        "fqt": "0",
        "secid": f"1.513310",  # 上交所 1.代码
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


def main() -> None:
    df = fetch_kline()
    print("总行数:", len(df))
    print("\n前 3 行:")
    print(df.head(3).to_string())
    dates = df["时间"].str[:10].unique()
    print(f"\n覆盖交易日({len(dates)}): {dates[0]} ~ {dates[-1]}")
    print(f"每日 bar 数示例（首日）: {(df['时间'].str[:10] == dates[0]).sum()}")

    out = PROJECT_ROOT / "data" / "bt_export" / "513310_5min_raw.csv"
    df.to_csv(out, index=False)
    print(f"\n已存 -> {out}")


if __name__ == "__main__":
    main()
