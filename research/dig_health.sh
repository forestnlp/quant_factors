#!/usr/bin/env bash
# dig 健康哨兵：独立于监工的"第二双眼睛"（cron 每 30 分钟拉一次）。
# 监工会自愈，但没人盯"监工+cron 双双哑火"的静默态——本脚本专治此症：
# 任一异常即写 data/derived/dig_health.log（人只看这一个文件即可掌握生死）。
# 手动查：bash research/dig_health.sh
set -u
ROOT="/home/chinapost/users/jaycode/quant_factors"
cd "$ROOT" || exit 1
HB="data/derived/dig_log.jsonl"
HL="data/derived/dig_health.log"
STALE=5400          # 心跳停更告警线（秒）：正常一轮 3-4 分钟，1.5h=铁定出事

ts() { date '+%F %T'; }
bad=""
age=$(( $(date +%s) - $(stat -c %Y "$HB" 2>/dev/null || echo 0) ))
pgrep -f "dig_supervisor.sh" >/dev/null || bad="$bad 监工不在;"
# 挖掘批缺席本身不算病（收工冷却期常态）；监工不在 或 心跳停更 才是死相
[ "$age" -gt "$STALE" ] && bad="$bad 心跳停更${age}s;"

if [ -n "$bad" ]; then
  echo "[$(ts)] 异常 →$bad" >> "$HL"
else
  echo "[$(ts)] 健康（心跳 ${age}s 前）" >> "$HL"
fi
tail -20 "$HL" > "$HL.tmp" && mv "$HL.tmp" "$HL"   # 只留近 20 条
