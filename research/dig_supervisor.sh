#!/usr/bin/env bash
# dig 监工：让 L4 挖掘批"永远有一批活着"。
#   批崩溃/LLM 断连(dig 以 rc=3 退出) → 指数退避重启（上限 2h，绝不无脑热循环）
#   心跳卡死（进程在但 dig_log.jsonl 30 分钟没动）→ 杀 hung 进程重开
#   正常收工（预算/止损停机 rc=0）→ 冷却 10 分钟后开下一批
# 保活双保险：本脚本常驻自监控；cron 每 30 分钟拉一次（flock 单实例，已有活实例则秒退）。
set -u
ROOT="/home/chinapost/users/jaycode/quant_factors"
cd "$ROOT" || exit 1
CONDA="/data/anaconda3/bin/conda"
LOG="data/derived/dig_supervisor.log"
LOCK="data/derived/dig_supervisor.lock"
HB="data/derived/dig_log.jsonl"
BATCH_LOG="data/derived/dig_batch_auto.log"
STALE=1800            # 心跳停更判定（秒）：一轮约 3-4 分钟，30 分钟极宽裕
COOLDOWN=600          # 正常收工后的冷却（秒）
MAXSLEEP=7200         # 故障退避上限（秒）

exec 9>"$LOCK"
flock -n 9 || exit 0   # 已有活监工，本实例退出

ts() { date '+%F %T'; }
fail=0
while true; do
  if pgrep -f "python -m research\.dig run" >/dev/null; then
    hb_age=$(( $(date +%s) - $(stat -c %Y "$HB" 2>/dev/null || echo 0) ))
    if [ "$hb_age" -gt "$STALE" ]; then
      echo "[$(ts)] 心跳停更 ${hb_age}s → 判 hung，杀掉重开" >> "$LOG"
      pkill -f "conda run -n jaycode python -m research.dig run" 2>/dev/null
      pkill -f "python -m research.dig run" 2>/dev/null
      sleep 30
    fi
    sleep 60
  else
    echo "[$(ts)] 无挖掘进程 → 开新批 (rounds=20 patience=5)" >> "$LOG"
    "$CONDA" run -n jaycode python -m research.dig run \
      --rounds 20 --patience 5 >> "$BATCH_LOG" 2>&1
    rc=$?
    if [ "$rc" -eq 0 ]; then
      fail=0
      echo "[$(ts)] 批正常收工（rc=0，含止损/预算停机）→ 冷却 $((COOLDOWN/60)) 分钟" >> "$LOG"
      sleep "$COOLDOWN"
    else
      fail=$((fail + 1))
      wait_s=$(( COOLDOWN * 2**fail ))
      [ "$wait_s" -gt "$MAXSLEEP" ] && wait_s=$MAXSLEEP
      echo "[$(ts)] 批异常退出 rc=$rc（infra 故障/LLM 断连）第 ${fail} 次 → ${wait_s}s 后重试" >> "$LOG"
      sleep "$wait_s"
    fi
  fi
done
