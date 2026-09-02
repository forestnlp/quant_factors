# -*- coding: utf-8 -*-
"""取数任务：聚宽 → 本地 CSV 原始层

设计要点（对应踩坑教训）：
    - 分片 + 断点续跑：已有分片直接跳过，认证/网络失败可在原地续跑。
    - fail-fast：认证失效立即中止整批，不把失败当"该分片无数据"继续（教训 3）。
    - 落盘即核对：每片打印行数/日期范围，收尾打印总覆盖区间（教训 4）。
    - 上传云端的脚本只含取数逻辑，不含本项目任何结论与凭据（规则 8）。

用法（按顺序）：
    conda run -n jaycode python -m research.fetch calendar          # 最先：交易日历
    conda run -n jaycode python -m research.fetch probe             # 通道与体积探针
    conda run -n jaycode python -m research.fetch daily             # 全历史日线(2005起)
    conda run -n jaycode python -m research.fetch auction --start 2010-01-01
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research import jq_channel as jq
from research.config import raw_dir

# ---------------------------------------------------------------- 云端脚本模板
# 仅取数逻辑：拉数据 → to_csv 到 jq_out/。不得掺入本项目因子/结论/凭据。

DAILY_TMPL = '''# -*- coding: utf-8 -*-
from jqdata import *
import os
import pandas as pd

DAYS = {days!r}
RAW_FIELDS = ["open", "close", "high", "low", "volume", "money",
              "high_limit", "low_limit", "paused"]
POST_FIELDS = ["open", "high", "low", "close"]
os.makedirs("jq_out", exist_ok=True)
codes = get_all_securities("stock", date=DAYS[-1]).index.tolist()


def pull(fq, fields):
    parts = []
    for i in range(0, len(codes), 1500):        # 分组避开单次返回上限
        parts.append(get_price(codes[i:i + 1500], start_date=DAYS[0],
                               end_date=DAYS[-1], fields=fields, fq=fq,
                               panel=False, skip_paused=False))
    d = pd.concat(parts, ignore_index=True)
    d["time"] = d["time"].astype(str).str[:10]
    return d


raw = pull(None, RAW_FIELDS)                     # 真实价（不复权，PIT 安全）
post = pull("post", POST_FIELDS)                 # 后复权（历史不被未来分红改写）
post = post.rename(columns={{f: "post_" + f for f in POST_FIELDS}})
df = raw.merge(post[["time", "code"] + ["post_" + f for f in POST_FIELDS]],
               on=["time", "code"], how="left")
p = os.path.join("jq_out", "{fname}")
df.to_csv(p, index=False)
print("rows=%d codes=%d days=%d size=%.1fMB" % (
    len(df), df["code"].nunique(), df["time"].nunique(),
    os.path.getsize(p) / 1048576.0))
'''

CALENDAR_TMPL = '''# -*- coding: utf-8 -*-
from jqdata import *
import os, datetime

days = sorted(str(d) for d in get_all_trade_days())
today = str(datetime.date.today())
days = [d for d in days if d <= today]        # 剔除平台预置的未来占位日
os.makedirs("jq_out", exist_ok=True)
with open("jq_out/{fname}", "w") as f:
    f.write("\\n".join(days) + "\\n")
print("days=%d %s ~ %s" % (len(days), days[0], days[-1]))
'''

AUCTION_TMPL = '''# -*- coding: utf-8 -*-
from jqdata import *
import os

DAYS = {days!r}
FIELDS = ["time", "current", "a1_v", "b1_v", "volume", "money"]
os.makedirs("jq_out", exist_ok=True)
out = []
for d in DAYS:
    codes = get_all_securities("stock", date=d).index.tolist()
    for i in range(0, len(codes), 2500):        # 竞价单次上限 5000 行
        a = get_call_auction(codes[i:i + 2500], start_date=d, end_date=d, fields=FIELDS)
        a["day"] = d
        out.append(a)
df = __import__("pandas").concat(out, ignore_index=True)
p = os.path.join("jq_out", "{fname}")
df.to_csv(p, index=False)
print("rows=%d size=%.1fMB" % (len(df), os.path.getsize(p) / 1048576.0))
'''

PROBE_TMPL = '''# -*- coding: utf-8 -*-
from jqdata import *
import os, time

END = {end!r}
RAW_FIELDS = ["open", "close", "high", "low", "volume", "money",
              "high_limit", "low_limit", "paused"]
all_st = get_all_securities("stock")
print("[1] 标的总数 %d 列=%s" % (len(all_st), list(all_st.columns)))
_end = all_st["end_date"].astype(str)
print("    退市(end_date<2025) %d 只" % int((_end < "2025-01-01").sum()))
codes = list(all_st.index)

t0 = time.time()
dn = get_price(codes, end_date=END, count=60, fields=RAW_FIELDS, fq=None,
               panel=False, skip_paused=False)
print("[2] 全市场x60日 rows=%d 耗时=%.1fs" % (len(dn), time.time() - t0))
os.makedirs("jq_out", exist_ok=True)
p = "jq_out/probe_daily.csv"
dn.to_csv(p, index=False)
print("[3] raw csv=%.1fMB" % (os.path.getsize(p) / 1048576.0))
print("PROBE_DONE")
'''


# ---------------------------------------------------------------- 通用分片执行

def _chunks(days: list[str], size: int) -> list[list[str]]:
    return [days[i:i + size] for i in range(0, len(days), size)]


def _fetch_series(name: str, tmpl: str, start: str, end: str, chunk_days: int,
                  out_dir: Path, force: bool) -> None:
    """按交易日分片拉取一类数据；断点续跑 + 认证失败立即中止 + 收尾覆盖核对。"""
    days = jq.trading_days(start, end)
    if not days:
        raise SystemExit(f"本地日历无 {start}~{end}，无法切片"
                         f"（先执行: python -m research.fetch calendar）")
    out_dir.mkdir(parents=True, exist_ok=True)
    todo, done = [], 0
    for ch in _chunks(days, chunk_days):
        f = out_dir / f"{name}_{ch[0]}_{ch[-1]}.csv"
        if f.exists() and not force:
            done += 1
        else:
            todo.append((ch, f))
    print(f"[{name}] 交易日 {len(days)} 天 / 分片 {done + len(todo)} 个"
          f"（已存在 {done}，本次取 {len(todo)}）")

    for i, (ch, f) in enumerate(todo, 1):
        print(f"  [{i}/{len(todo)}] {ch[0]} ~ {ch[-1]}", flush=True)
        try:
            jq.run_script(tmpl.format(days=ch, fname=f.name), f.name, f)
        except jq.JqAuthError as e:
            print(f"  [中止] {e}")
            print(f"  已完成 {done + i - 1}/{done + len(todo)} 片，"
                  f"更新凭据后重跑同一命令即可续传")
            return
        n = sum(1 for _ in open(f, encoding="utf-8")) - 1
        print(f"      -> {n} 行")

    _coverage(name, sorted(out_dir.glob(f"{name}_*.csv")))


def _coverage(name: str, files: list[Path]) -> None:
    """落盘后核对覆盖区间（教训 1/4：不读回核对等于没取到）。"""
    if not files:
        print(f"[{name}] 无文件，覆盖核对跳过")
        return
    total, lo, hi = 0, None, None
    for f in files:
        s, e = f.stem.split("_")[-2], f.stem.split("_")[-1]
        lo = s if lo is None or s < lo else lo
        hi = e if hi is None or e > hi else hi
        total += sum(1 for _ in open(f, encoding="utf-8")) - 1
    print(f"[{name}] 覆盖核对: {len(files)} 片, {total} 行, 区间 {lo} ~ {hi}")


# ---------------------------------------------------------------- 任务入口

def probe(end: str = "2026-08-13") -> None:
    """通道与吞吐探针：测认证、标的是否含退市、单次可取规模与 csv 体积。"""
    from research.config import PROJECT_ROOT

    print("[probe] 检查聚宽通道认证 ...")
    jq.check_auth()
    print("[probe] 认证可用，云端执行探针 ...")
    stage = PROJECT_ROOT / "data" / "_stage"
    stage.mkdir(parents=True, exist_ok=True)
    p = stage / "_probe.py"
    p.write_text(PROBE_TMPL.format(end=end), encoding="utf-8")
    try:
        out = jq._jqcli("research", "exec", "--file", str(p),
                        "--execution-timeout", "600", "--yes", timeout=700)
        print(json.dumps(out, ensure_ascii=False)[:4000])
    finally:
        p.unlink(missing_ok=True)


def fetch_calendar() -> None:
    """拉取交易日历到 raw 层（所有分片切分以它为准，须最先执行）。"""
    from research.jq_channel import calendar_path, run_script

    out = calendar_path()
    run_script(CALENDAR_TMPL.format(fname=out.name), out.name, out)
    days = [ln.strip() for ln in out.read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    print(f"[calendar] 覆盖核对: {len(days)} 个交易日, {days[0]} ~ {days[-1]}")


def fetch_daily(start: str, end: str, chunk_days: int = 60, force: bool = False) -> None:
    """全市场日线（真实价+后复权，含涨跌停价/停牌）→ data/raw/jq/daily/"""
    _fetch_series("daily", DAILY_TMPL, start, end, chunk_days,
                  raw_dir("jq", "daily"), force)


def fetch_auction(start: str, end: str, chunk_days: int = 10, force: bool = False) -> None:
    """集合竞价（9:25 虚拟撮合）→ data/raw/jq/auction/"""
    _fetch_series("auction", AUCTION_TMPL, start, end, chunk_days,
                  raw_dir("jq", "auction"), force)


def main() -> None:
    ap = argparse.ArgumentParser(description="聚宽取数任务")
    ap.add_argument("task", choices=["calendar", "probe", "daily", "auction"])
    ap.add_argument("--start", default="2005-01-04",
                    help="聚宽行情起点为 2005-01-04（官方文档+实测）")
    ap.add_argument("--end", default="2026-08-13")
    ap.add_argument("--chunk-days", type=int, default=0,
                    help="每片交易日数（日线默认 60，竞价默认 10）")
    ap.add_argument("--force", action="store_true", help="重取已存在分片")
    a = ap.parse_args()

    if a.task == "calendar":
        fetch_calendar()
    elif a.task == "probe":
        probe(a.end)
    elif a.task == "daily":
        fetch_daily(a.start, a.end, a.chunk_days or 60, a.force)
    else:
        fetch_auction(a.start, a.end, a.chunk_days or 10, a.force)


if __name__ == "__main__":
    main()
