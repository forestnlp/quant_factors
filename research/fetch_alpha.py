# -*- coding: utf-8 -*-
"""官方 alpha101 基线取数（"对答案战役"标准答案）

jqfactor.get_all_alpha_values(date,'101') 返回全市场当日 101 个官方因子值，
历史深度实测 2020-01-02 起（非全 NaN 因子 82 个）。

采样策略：每 5 个交易日取一天（与标签 fwd_ret_5 对齐 → 样本间不重叠，
RankIC 序列近似独立），每片 10 个采样日。断点续跑按分片文件名跳过。

输出：data/raw/jq/alpha_ref/alpha101_YYYY-MM-DD_YYYY-MM-DD.csv
      列：day, code, alpha_001..alpha_101（宽表）

用法：conda run -n jaycode python -m research.fetch_alpha \
        --start 2020-01-02 --end 2026-09-02
"""

from __future__ import annotations

import argparse
from pathlib import Path

from research import jq_channel as jq
from research.config import raw_dir

STEP = 5          # 采样步长（交易日），= 标签视野
DATES_PER_CHUNK = 10

# 通道纪律：同一时刻只允许一个取数进程走云端通道（实测并发会撞临时内核，
# 表现为 download 报 not_found）。本脚本启动即自检，避免与 fetch/update 并跑。

ALPHA_TMPL = '''# -*- coding: utf-8 -*-
import os
import pandas as pd
from jqfactor import get_all_alpha_values

DAYS = {days!r}
os.makedirs("jq_out", exist_ok=True)
parts = []
for d in DAYS:
    df = get_all_alpha_values(d, "101")
    df["day"] = d
    df = df.reset_index()
    parts.append(df)
out = pd.concat(parts, ignore_index=True)
p = os.path.join("jq_out", "{fname}")
out.to_csv(p, index=False)
print("rows=%d size=%.1fMB" % (len(out), os.path.getsize(p) / 1048576.0))
'''


def fetch_alpha(start: str, end: str, force: bool = False) -> None:
    out_dir = raw_dir("jq", "alpha_ref")
    out_dir.mkdir(parents=True, exist_ok=True)
    days = jq.trading_days(start, end)[::STEP]
    chunks = [days[i:i + DATES_PER_CHUNK]
              for i in range(0, len(days), DATES_PER_CHUNK)]
    print(f"采样日 {len(days)} 个（步长 {STEP}），分 {len(chunks)} 片")
    for ch in chunks:
        fname = f"alpha101_{ch[0]}_{ch[-1]}.csv"
        local = out_dir / fname
        if local.exists() and not force:
            continue
        print(f"取 {fname} ...", flush=True)
        script = ALPHA_TMPL.format(days=ch, fname=fname)
        jq.run_script(script, fname, local, timeout=900, exec_timeout=600.0)
    print(f"完成：{len(list(out_dir.glob('alpha101_2*.csv')))} 片在盘")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="官方 alpha101 基线取数")
    ap.add_argument("--start", default="2020-01-02")
    ap.add_argument("--end", default="2026-09-02")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    jq.check_auth()
    fetch_alpha(a.start, a.end, a.force)
