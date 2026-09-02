# -*- coding: utf-8 -*-
"""聚宽云端取数通道（jqcli 三段式）

机制（已实测）：本地生成「只含取数逻辑」的脚本 → `jqcli research exec` 在云端
临时内核执行 → 脚本把结果 `to_csv` 写进云端 `jq_out/` → `jqcli research download`
拉回本地 → 立即删除云端文件（配额有限）。

硬约束（实测/官方文档）：
    - 云端单次执行默认 120s 超时 → 任务必须分片
    - 单次返回行数有上限（竞价 5000 行）→ 标的须分组
    - 云端研究会话 Cookie 会被回收 → 认证失败必须 fail-fast，不得静默重试到底

凭据只从 `.env` 的 `JQCLI_COOKIE` 读取，不写代码、不入库、不出项目目录。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from research.config import PROJECT_ROOT, jqcli_bin

CLOUD_OUT_DIR = "jq_out"


class JqAuthError(RuntimeError):
    """聚宽认证失效（Cookie 过期/会话被回收）。须人工更新 .env 后重跑。"""


def _parse(stdout: str) -> dict:
    """jqcli --format json 的返回解析；认证类错误抛 JqAuthError 以便上层中止。"""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"raw": stdout}
    err = data.get("error") or {}
    if err.get("code") in ("not_authenticated", "auth_failed", "session_expired"):
        raise JqAuthError(
            f"聚宽认证失效（{err.get('code')}）：请更新 .env 的 JQCLI_COOKIE 后重跑，"
            f"剩余分片可用断点续跑补齐")
    return data


def _jqcli(*args: str, timeout: int = 300, input_text: str | None = None) -> dict:
    """调用项目内 jqcli 并解析 JSON。基础设施异常一律上抛，不吞。"""
    exe = jqcli_bin()
    if not exe.exists():
        raise FileNotFoundError(f"缺少 jqcli: {exe}（见 PROJECT.md 环境节三步重建）")
    r = subprocess.run(
        [str(exe), "--env-file", str(PROJECT_ROOT / ".env"),
         "--format", "json", "--non-interactive", *args],
        capture_output=True, text=True, timeout=timeout, cwd=str(PROJECT_ROOT),
        input=input_text)
    out = _parse(r.stdout or "")
    if r.returncode != 0:
        raise RuntimeError(f"jqcli 失败: {(r.stderr or r.stdout or '')[:300]}")
    return out


def check_auth() -> bool:
    """真实探测取数通道可用性：跑一行云端代码。

    注意 `research kernels` 等只读命令**不需要登录会话**，拿它探测会在
    Cookie 已失效时误报"可用"（实测），故必须用 exec 实际执行来验证。
    """
    tmp = _jqcli("research", "exec", "--code-stdin", "--yes",
                 input_text='print("AUTH_OK")', timeout=180)
    if "AUTH_OK" not in json.dumps(tmp, ensure_ascii=False):
        raise RuntimeError(f"云端探测异常: {json.dumps(tmp, ensure_ascii=False)[:300]}")
    return True


def _acquire_channel_lock(stage: Path):
    """云端通道独占锁：同一时刻只允许一个取数进程（实测并发会撞云端临时内核，
    表现为 download 报 not_found）。返回锁文件句柄；被占用抛 RuntimeError。"""
    import os
    lock = stage / ".channel.lock"
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            return fd
        except FileExistsError:
            try:  # 陈旧锁（持有进程已死）则清掉重试一次
                pid = int(lock.read_text().strip() or "0")
                if Path(f"/proc/{pid}").exists():
                    break
                lock.unlink(missing_ok=True)
            except (ValueError, OSError):
                lock.unlink(missing_ok=True)
    raise RuntimeError(
        f"聚宽通道被进程 {lock.read_text() if lock.exists() else '?'} 占用，禁止并发取数")


def run_script(script: str, remote_name: str, local_out: Path,
               timeout: int = 900, exec_timeout: float = 600.0) -> Path:
    """云端执行取数脚本，把产出 csv 拉到 local_out；无论成败都清理云端与本地脚本。

    exec_timeout 是**远端**执行超时（jqcli 默认仅 120s，分片大小时必须显式放宽），
    timeout 是本地 subprocess 等待上限，两者须同步考虑。
    local_out 由调用方决定位置（须在 data/ 内）。产出为空/过小视为失败。
    """
    stage = PROJECT_ROOT / "data" / "_stage"
    stage.mkdir(parents=True, exist_ok=True)
    fd = _acquire_channel_lock(stage)
    local_script = stage / f"_{remote_name}.py"
    local_script.write_text(script, encoding="utf-8")
    try:
        resp = _jqcli("research", "exec", "--file", str(local_script),
                      "--execution-timeout", str(exec_timeout), "--yes",
                      timeout=timeout)
        # 云端执行报错时 jqcli 仍返回 0，若不检查就 download 只会得到
        # not_found（下游症状），真因被吞——必须把 exec 错误原样抛出
        if resp.get("status") == "error":
            o = (resp.get("outputs") or [{}])[0]
            raise RuntimeError(
                f"云端执行失败: {o.get('ename')}: {str(o.get('evalue'))[:300]}")
        _jqcli("research", "download", f"{CLOUD_OUT_DIR}/{remote_name}",
               "-o", str(local_out), "--force", timeout=300)
    finally:
        try:
            _jqcli("research", "rm", f"{CLOUD_OUT_DIR}/{remote_name}",
                   "--yes", timeout=120)
        except Exception:  # noqa: BLE001 - 清理失败不影响取数结果
            pass
        local_script.unlink(missing_ok=True)
        import os
        os.close(fd)
        (stage / ".channel.lock").unlink(missing_ok=True)
    if not local_out.exists() or local_out.stat().st_size < 100:
        raise RuntimeError(f"云端未产出有效文件: {remote_name}")
    return local_out


CALENDAR_FILE = "trading_calendar.csv"


def calendar_path() -> Path:
    """交易日历本地缓存（raw 层，由 `fetch calendar` 从聚宽落盘）。"""
    from research.config import raw_dir

    return raw_dir("jq") / CALENDAR_FILE


def trading_days(start: str, end: str) -> list[str]:
    """取区间内交易日列表，以 `fetch calendar` 落盘的聚宽日历为准。

    聚宽行情自 2005-01-04 起（官方文档与实测一致），其 get_all_trade_days
    还含未来占位日，落盘时已截断。
    """
    p = calendar_path()
    if not p.exists():
        raise SystemExit(f"缺少交易日历 {p}，先执行: python -m research.fetch calendar")
    days = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    return [d for d in days if start <= d <= end]
