# -*- coding: utf-8 -*-
"""抓取中韩半导体ETF(513310)历史日线并本地化存储（实验区）

数据源：AKShare fund_etf_hist_em（东方财富）
输出：data/bt_export/513310_daily.csv

用法：
    conda run -n jaycode python playground/fetch_513310.py

成功标准：
    脚本无异常退出，生成 CSV，打印行数与最新日期。
"""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SYMBOL = "513310"
OUT = PROJECT_ROOT / "data" / "bt_export" / f"{SYMBOL}_daily.csv"

START_DATE = "20200101"
END_DATE = "20300101"


def main() -> None:
    import akshare as ak

    print(f"正在拉取 {SYMBOL} 日线 ...")
    df = ak.fund_etf_hist_em(
        symbol=SYMBOL,
        period="daily",
        start_date=START_DATE,
        end_date=END_DATE,
        adjust="",  # 不复权：用于纯价差择时回测，避免复权引入未来信息
    )
    if df is None or df.empty:
        raise SystemExit("未获取到数据，请检查网络或代码是否有效。")

    # 标准化列名并保留关键字段（与 qlib/策略所需对齐）
    df = df.rename(columns={
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
    })
    keep = ["date", "open", "high", "low", "close", "volume", "amount"]
    df = df[keep].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)

    print(f"已保存 {len(df)} 行 -> {OUT}")
    print(f"区间: {df['date'].min().date()} ~ {df['date'].max().date()}")


if __name__ == "__main__":
    main()
