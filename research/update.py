# -*- coding: utf-8 -*-
"""一键每日增量更新（手动执行，不建定时任务）

用法（明天试）：
    conda run -n jaycode python -m research.update              # 自动补到最新
    conda run -n jaycode python -m research.update --through 2026-09-04 --deep

逻辑（自动补齐，幂等——跑几次结果一样，中断重跑即续）：
    1) 刷新交易日历（识别新交易日）
    2) 每个数据集从已落盘分片文件名解析"最后日期"，只取缺口增量；
       分片只追加不覆盖，缺口跨多个旧片也不影响（build/check 按主键去重）
    3) 出数节奏口径：
       - 盘后即有（daily / auction / billboard / st）→ 补到 ≤today 的最新交易日
       - T+1 公布（valuation / money_flow / mtss）  → 补到上一交易日，宁缺毋假
    4) 过 check 体检门（--deep 加对抗审计与增强件体检）→ 重建 L2 宽表

季度类（industry / concept / finance）不进日更，按其节奏手动补跑对应 fetch 命令。
"""

from __future__ import annotations

import argparse

from research import jq_channel as jq
from research import build, check, fetch
from research.config import raw_dir


def _latest_local(name: str) -> str:
    """从分片文件名解析该数据集已落盘的最后日期（YYYY-MM-DD）。"""
    ends = []
    for f in raw_dir("jq", name).glob(f"{name}_*.csv"):
        parts = f.stem[len(name) + 1:].split("_")
        if len(parts) >= 2 and len(parts[-1]) == 10:
            ends.append(parts[-1])
    return max(ends) if ends else ""


# 数据集 → (fetch 函数, 是否 T+1 公布)
DAILY_SETS = {
    "daily":      (fetch.fetch_daily, False),
    "auction":    (fetch.fetch_auction, False),
    "billboard":  (fetch.fetch_billboard, False),
    "st":         (fetch.fetch_st, False),
    "valuation":  (fetch.fetch_valuation, True),
    "money_flow": (fetch.fetch_moneyflow, True),
    "mtss":       (fetch.fetch_mtss, True),
}


def main() -> None:
    ap = argparse.ArgumentParser(description="数据一键增量更新（自动补到最新）")
    ap.add_argument("--through", default="", help="更新截止日，默认今天")
    ap.add_argument("--deep", action="store_true",
                    help="体检加对抗审计 + 增强件校验（较慢）")
    ap.add_argument("--no-build", action="store_true", help="跳过 L2 重建")
    a = ap.parse_args()
    today = a.through or __import__("datetime").date.today().isoformat()

    print(f"===== 更新开始，目标截止 {today} =====")
    print("[1/4] 刷新交易日历 ...")
    fetch.fetch_calendar()
    all_days = jq.trading_days("2005-01-04", "2999-12-31")
    upto = [d for d in all_days if d <= today]
    if not upto:
        raise SystemExit(f"日历中无 <= {today} 的交易日，检查 --through")
    last_td = upto[-1]                       # 最新交易日
    prev_td = upto[-2] if len(upto) > 1 else last_td

    print(f"[2/4] 逐数据集补缺口（最新交易日={last_td}，T+1 口径止={prev_td}）")
    for name, (fn, t1) in DAILY_SETS.items():
        end = prev_td if t1 else last_td
        latest = _latest_local(name)
        start_next = [d for d in all_days if d > latest]
        need = [d for d in start_next if d <= end]
        if not need:
            print(f"  {name:12s}: 已到 {latest}，无缺口 ✓")
            continue
        print(f"  {name:12s}: 本地到 {latest}，补 {need[0]} ~ {need[-1]}"
              f"（{len(need)} 天）", flush=True)
        fn(need[0], need[-1])

    print("[3/4] 数据体检门 ...")
    check.main()
    if a.deep:
        check.deep_rules()
        check.new_sets()

    if a.no_build:
        print("[4/4] 跳过 L2 重建（--no-build）")
    else:
        print("[4/4] 重建 L2 宽表 ...")
        build.main()
    print("===== 更新完成 =====")


if __name__ == "__main__":
    main()
