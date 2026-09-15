# -*- coding: utf-8 -*-
"""官方 alpha101 基线取数（"对答案战役"标准答案 + 收编战役日频版）

jqfactor.get_all_alpha_values(date,'101') 返回全市场当日 101 个官方因子值，
历史深度实测 2020-01-02 起（非全 NaN 因子 82 个）。

两种用法：
  1) 榜单哨兵（原用途）：每 STEP=5 个交易日采一天（与 fwd_ret_5 对齐、样本不重叠）
  2) 收编进 ML 特征池（2026-09-15）：--step 1 --cols alpha_016,alpha_088,...
     只留白名单列，日频全史。放弃本地复算的原因：Top15 涉及 16 种算子
     （decay_linear/ts_rank/product/截面 correlation），复刻 jqlib 语义风险高、
     且对答案本身也要同等机时 → 官方原值直取更便宜更可靠。

输出：data/raw/jq/alpha_ref/[cols<标签>_]alpha101_起_止.csv
      列：day, code, alpha_xxx[, ...]（宽表）

用法：conda run -n jaycode python -m research.fetch_alpha \
        --start 2020-01-02 --end 2026-09-02 [--step 5] [--cols a,b] [--tag top15]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from research import jq_channel as jq
from research.config import raw_dir

STEP = 5          # 采样步长（交易日）；--step 1 即全日频
DATES_PER_CHUNK = 10

# 通道纪律：同一时刻只允许一个取数进程走云端通道（实测并发会撞临时内核，
# 表现为 download 报 not_found）。本脚本启动即自检，避免与 fetch/update 并跑。

ALPHA_TMPL = '''# -*- coding: utf-8 -*-
import os
import pandas as pd
from jqfactor import get_all_alpha_values

# get_all_alpha_values 第二参数只认 '101'/'191'（实测不能按列名筛），
# 故云端算全量、下载前裁列（KEEP 空=留全部），省下载体积。
DAYS = {days!r}
KEEP = {keep!r}
os.makedirs("jq_out", exist_ok=True)
parts = []
for d in DAYS:
    df = get_all_alpha_values(d, {lib!r})
    df["day"] = d
    parts.append(df.reset_index())
out = pd.concat(parts, ignore_index=True)
if KEEP:
    cols = [c for c in out.columns if c in ("day", "code") or c in KEEP]
    out = out[cols]
p = os.path.join("jq_out", "{fname}")
out.to_csv(p, index=False)
print("rows=%d cols=%d size=%.1fMB" % (
    len(out), out.shape[1], os.path.getsize(p) / 1048576.0))
'''


def fetch_alpha(start: str, end: str, force: bool = False,
                step: int = STEP, cols: list[str] | None = None,
                tag: str = "", lib: str = "101") -> None:
    """cols=None 取全库；给定列名列表则只取那些（省 90% 体积）。lib∈101/191。"""
    out_dir = raw_dir("jq", "alpha_ref")
    out_dir.mkdir(parents=True, exist_ok=True)
    days = jq.trading_days(start, end)[::step]
    chunks = [days[i:i + DATES_PER_CHUNK]
              for i in range(0, len(days), DATES_PER_CHUNK)]
    pref = f"{tag}_" if tag else ""
    print(f"取数日 {len(days)} 个（步长 {step}，库 {lib}），分 {len(chunks)} 片"
          f"{'，列白名单 ' + str(len(cols)) + ' 支' if cols else ''}")
    for ch in chunks:
        fname = f"{pref}alpha{lib}_{ch[0]}_{ch[-1]}.csv"
        local = out_dir / fname
        if local.exists() and not force:
            continue
        print(f"取 {fname} ...", flush=True)
        script = ALPHA_TMPL.format(days=ch, keep=cols or [], lib=lib,
                                   fname=fname)
        jq.run_script(script, fname, local, timeout=900, exec_timeout=600.0)
    n = len(list(out_dir.glob(f"{pref}alpha{lib}_2*.csv")))
    print(f"完成：{n} 片在盘")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="官方 alpha101 基线取数")
    ap.add_argument("--start", default="2020-01-02")
    ap.add_argument("--end", default="2026-09-02")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--step", type=int, default=STEP,
                    help="采样步长（交易日），1=全日频")
    ap.add_argument("--cols", default="",
                    help="列白名单（逗号分隔，如 alpha_016,alpha_088），空=全部")
    ap.add_argument("--tag", default="", help="文件名前缀（区分不同取法）")
    ap.add_argument("--lib", default="101", choices=["101", "191"],
                    help="官方因子库（191=Alpha191，2026-09-15 探针实测 188 列非全NaN）")
    a = ap.parse_args()
    jq.check_auth()
    fetch_alpha(a.start, a.end, a.force, a.step,
                [c.strip() for c in a.cols.split(",") if c.strip()], a.tag,
                a.lib)
