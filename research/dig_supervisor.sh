#!/usr/bin/env bash
# dig 监工：让 L4 挖掘批"永远有一批活着"。
#   批崩溃/LLM 断连(dig 以 rc=3 退出) → 指数退避重启（上限 2h，绝不无脑热循环）
#   心跳卡死（进程在但 dig_log.jsonl 30 分钟没动）→ 杀 hung 进程重开
#   正常收工（预算/止损停机 rc=0）→ 冷却 10 分钟后开下一批
# 保活双保险：本脚本常驻自监控；cron 每 30 分钟拉一次（flock 单实例，已有活实例则秒退）。
set -u
ROOT="/home/chinapost/users/jaycode/quant_factors"
cd "$ROOT" || exit 1
# 直连 env python（绕过 conda run 包装层：两次 rc=139 均为开批 1-2 秒、首行输出前即崩，
# 高度指向 conda run 包装层段错误；去掉中间层后 rc 直接反映 python 本体）
PYENV="/home/chinapost/.conda/envs/jaycode/bin/python"
LOG="data/derived/dig_supervisor.log"
LOCK="data/derived/dig_supervisor.lock"
HB="data/derived/dig_log.jsonl"
BATCH_LOG="data/derived/dig_batch_auto.log"
STALE=3600            # 心跳停更判定（秒）（09-11 放宽 1800→3600：深思考单轮最坏
                      #   = 畸变重试 2×900s 超时 + 机审 ≈38 分钟，30 分钟线会误杀健康批）
COOLDOWN=180          # 正常收工后的冷却（秒）（09-11 加速：600→180，本地 LLM 无限流，冷却纯属浪费；
                      #   故障退避仍按 180×2^fail 指数爬升，不无脑热循环）
MAXSLEEP=7200         # 故障退避上限（秒）

exec 9>"$LOCK"
flock -n 9 || exit 0   # 已有活监工，本实例退出

# 教训 09-10：kill 监工时其 sleep 子进程会孤儿化并继承锁 fd → 新实例被 flock
# 挡在门外"静默复活失败"。退避/冷却 sleep 一律后台化并登记，EXIT 时带走。
SP=""
trap '[ -n "$SP" ] && kill "$SP" 2>/dev/null' EXIT
sp() { sleep "$1" & SP=$!; wait "$SP" 2>/dev/null; SP=""; }   # 可中断 sleep

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
    # faulthandler：段错误(rc=139)时把 Python 栈打进批日志（两次 139 均零输出即崩，须留证）
    # 9>&-：挖批严禁继承监工的锁 fd（09-11 教训：监工被 kill 后，幸存挖批持有 fd9
    #   → flock 锁借尸还魂，新监工被挡、cron 也救不回，直到批自己退出）
    PYTHONFAULTHANDLER=1 "$PYENV" -m research.dig run \
      --rounds 20 --patience 5 >> "$BATCH_LOG" 2>&1 9>&-
    rc=$?
    if [ "$rc" -eq 0 ]; then
      fail=0
      echo "[$(ts)] 批正常收工（rc=0，含止损/预算停机）→ 冷却 $((COOLDOWN/60)) 分钟" >> "$LOG"
      sp "$COOLDOWN"
    else
      fail=$((fail + 1))
      wait_s=$(( COOLDOWN * 2**fail ))
      [ "$wait_s" -gt "$MAXSLEEP" ] && wait_s=$MAXSLEEP
      echo "[$(ts)] 批异常退出 rc=$rc（infra 故障/LLM 断连）第 ${fail} 次 → ${wait_s}s 后重试" >> "$LOG"
      sp "$wait_s"
    fi
  fi
done
