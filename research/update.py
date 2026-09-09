# -*- coding: utf-8 -*-
"""一键每日增量更新（手动执行，不建定时任务）

用法（明天试）：
    conda run -n jaycode python -m research.update              # 自动补到最新
    conda run -n jaycode python -m research.update --through 2026-09-04 --deep

逻辑（自动补齐，幂等——跑几次结果一样，中断重跑即续）：
    1) 刷新交易日历（识别新交易日）
    2) 每个数据集从已落盘分片文件名解析"最后日期"，只取缺口增量；
       分片只追加不覆盖，缺口跨多个旧片也不影响（build/check 按主键去重）
    3) 出数节奏口径（2026-09-08 因"盘中快照当收盘"事故升级为三档）：
       - close 档（daily / billboard）：量价是收盘终值，**只有晚于 CLOSE_HOUR
         才把 T 日算进缺口**，否则止于 T-1——盘中抓 T 日=半日快照毁数据
         （09-07 事故：10:54 抓的快照 close 86% 票不符、成交额缺一半，
         且 billboard 未公布被静默成空片、断点续跑永久跳过）
       - today 档（auction / st）：9:25 撮合完成/盘前已知，当日可更，
         但须过 AUCTION_HOUR（早晨竞价还不存在，09-09 实测炸过）
       - t1 档（valuation / money_flow / mtss）：T+1 公布，止于上一交易日
    4) 过 check 体检门（--deep 加深度校验）→ 重建 L2 宽表

季度类（industry / concept）与事件类（finance / finance_bs / finance_cf，
按报告期出数）不进日更，按其节奏手动补跑对应 fetch 命令（同样断点续跑）。
"""

from __future__ import annotations

import argparse
import datetime

from research import jq_channel as jq
from research import build, check, fetch
from research.config import raw_dir

CLOSE_HOUR = 20    # 收盘数据可信时点：晚 8 点后 T 日量价/龙虎榜才是终值
AUCTION_HOUR = 10  # 竞价可信时点：9:25 撮合完成，上午 10 点前 T 日竞价碰不得
                   # （09-09 晨间实测：8:50 取当日 auction → 云端无产出直接炸）


def _latest_local(name: str) -> str:
    """从分片文件名解析该数据集已落盘的最后日期（YYYY-MM-DD）。"""
    ends = []
    for f in raw_dir("jq", name).glob(f"{name}_*.csv"):
        parts = f.stem[len(name) + 1:].split("_")
        if len(parts) >= 2 and len(parts[-1]) == 10:
            ends.append(parts[-1])
    return max(ends) if ends else ""


# 数据集 → (fetch 函数, 节奏档)：close=收盘终值须晚 CLOSE_HOUR；today=当日可更；t1=T+1 公布
DAILY_SETS = {
    "daily":      (fetch.fetch_daily, "close"),
    "billboard":  (fetch.fetch_billboard, "close"),
    "auction":    (fetch.fetch_auction, "today"),
    "st":         (fetch.fetch_st, "today"),
    "valuation":  (fetch.fetch_valuation, "t1"),
    "money_flow": (fetch.fetch_moneyflow, "t1"),
    "mtss":       (fetch.fetch_mtss, "t1"),
}


def _gap_end(mode: str, last_td: str, prev_td: str, now: datetime.datetime) -> str:
    """按数据集节奏档算"允许补到的截止日"（盘中保护的核心判定）。"""
    if mode == "t1":
        return prev_td
    if mode == "today" and now.hour < AUCTION_HOUR:
        return prev_td          # 竞价 9:25 才撮合，早晨 T 日还不存在
    if mode == "close" and now.hour < CLOSE_HOUR:
        return prev_td          # 未过收盘可信时点，T 日数据碰不得
    return last_td


def main() -> None:
    ap = argparse.ArgumentParser(description="数据一键增量更新（自动补到最新）")
    ap.add_argument("--through", default="", help="更新截止日，默认今天")
    ap.add_argument("--deep", action="store_true",
                    help="体检加深度校验（较慢）")
    ap.add_argument("--no-build", action="store_true", help="跳过 L2 重建")
    a = ap.parse_args()
    now = datetime.datetime.now()
    today = a.through or now.date().isoformat()

    print(f"===== 更新开始，目标截止 {today}（现在 {now:%H:%M}）=====")
    print("[1/4] 刷新交易日历 ...")
    fetch.fetch_calendar()
    all_days = jq.trading_days("2005-01-04", "2999-12-31")
    upto = [d for d in all_days if d <= today]
    if not upto:
        raise SystemExit(f"日历中无 <= {today} 的交易日，检查 --through")
    last_td = upto[-1]                       # 最新交易日
    prev_td = upto[-2] if len(upto) > 1 else last_td

    print(f"[2/4] 逐数据集补缺口（最新交易日={last_td}；收盘档止="
          f"{_gap_end('close', last_td, prev_td, now)}，T+1 档止={prev_td}）")
    for name, (fn, mode) in DAILY_SETS.items():
        end = _gap_end(mode, last_td, prev_td, now)
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
