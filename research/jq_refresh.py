# -*- coding: utf-8 -*-
"""聚宽 Cookie 自动续期（治"研究平台会话被回收"的老毛病）

背景：取数走 jqcli 云端会话，聚宽会不定期回收会话 Cookie，表现为
`not_authenticated`，此前只能人工登录网页端复制 Cookie 回填 .env。
本脚本把这件事自动化：jqcli 自带 `auth login`（用户名 + 密码），
登录成功后 Cookie 存进 jqcli 本地配置，这里回写进 .env 供取数通道复用。

凭据（.env，已在 .gitignore 内）：
    JQCLI_USERNAME  聚宽账号（手机号/邮箱）
    JQCLI_PASSWORD  聚宽密码
    JQCLI_COOKIE    由本脚本自动维护（人工粘贴亦有效）

用法：
    python -m research.jq_refresh          # 探测：有效则什么都不做
    python -m research.jq_refresh --force  # 无条件重新登录并续票

退出码：0=凭据可用；1=续票失败（须人工处理，如聚宽加了验证码）。
铁律：认证失败绝不静默当业务失败（纪律5），故本脚本失败必须非零退出。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from research.config import PROJECT_ROOT, jqcli_bin

ENV_FILE = PROJECT_ROOT / ".env"


def _jqcli_config() -> Path:
    """jqcli 保存 cookie 的配置文件路径（与 jqcli/config.py 的 default 逻辑一致）。"""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "jqcli" / "config.json"
    return Path.home() / ".config" / "jqcli" / "config.json"


def _env_value(key: str) -> str:
    """从 .env 读一个键（不打印值）。"""
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        m = re.match(rf"^\s*{key}\s*=\s*(.*)$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""


def _write_env(key: str, value: str) -> None:
    """就地更新 .env 里某个键（保留其他行原样）；键不存在则追加。"""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    hit = False
    for i, line in enumerate(lines):
        if re.match(rf"^\s*{key}\s*=", line):
            lines[i] = f"{key}={value}"
            hit = True
            break
    if not hit:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _jqcli(*args: str, timeout: int = 180, input_text: str | None = None
           ) -> tuple[int, dict, str]:
    """调 jqcli，返回 (returncode, 解析后 JSON, stderr)。不抛异常，由上层判。"""
    exe = jqcli_bin()
    r = subprocess.run(
        [str(exe), "--env-file", str(ENV_FILE), "--format", "json",
         "--non-interactive", *args],
        capture_output=True, text=True, timeout=timeout, cwd=str(PROJECT_ROOT),
        input=input_text)
    try:
        data = json.loads(r.stdout or "")
    except json.JSONDecodeError:
        data = {"raw": (r.stdout or "")[:300]}
    return r.returncode, data, (r.stderr or "")


def check(retries: int = 3, wait: int = 8) -> bool:
    """真实探测云端可用性：必须 exec 一行代码（只读命令不需要会话，会误报）。

    新登录后研究平台要现建 JupyterHub 会话，首探有瞬时失败（实测），
    故带间隔重试；全部失败才判不可用。
    """
    for i in range(retries):
        try:
            rc, data, _ = _jqcli("research", "exec", "--code-stdin", "--yes",
                                 input_text='print("AUTH_OK")', timeout=180)
            if rc == 0 and "AUTH_OK" in json.dumps(data, ensure_ascii=False):
                return True
        except (subprocess.TimeoutExpired, OSError) as e:
            print(f"[探测] 通道异常: {type(e).__name__}: {e}")
        if i < retries - 1:
            time.sleep(wait)
    return False


def _cookie_from_jqcli_config() -> str:
    """登录成功后从 jqcli 本地配置取回 cookie。"""
    cfg = _jqcli_config()
    if not cfg.exists():
        return ""
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return str(data.get("cookie") or "").strip()


def login() -> bool:
    """用户名 + 密码登录，成功后把新 cookie 回写 .env 的 JQCLI_COOKIE。"""
    user = _env_value("JQCLI_USERNAME")
    pwd = _env_value("JQCLI_PASSWORD")
    if not user or not pwd:
        print("[中止] .env 缺 JQCLI_USERNAME / JQCLI_PASSWORD，无法自动续票")
        print("       请在 .env 补账号密码（.env 已 gitignore，不入库），"
              "或人工更新 JQCLI_COOKIE")
        return False
    rc, data, err = _jqcli("auth", "login", "--username", user,
                           "--password-stdin", input_text=pwd, timeout=180)
    if rc != 0:
        msg = (data.get("error") or {}).get("message") or err or json.dumps(
            data, ensure_ascii=False)
        print(f"[失败] 登录被拒: {str(msg)[:200]}")
        print("       若聚宽启用验证码/异地校验，只能人工登录网页端复制 Cookie。")
        return False
    # jqcli 把登录得到的 cookie 存进本地配置；取回后回写 .env。
    # 判据不拿 .env 旧值比较（长期自动续票后旧值本就是唯一可用票），
    # 只以"回写后能否真实探测"为准——探测不通就如实报失败，绝不假称续票成功。
    cookie = _cookie_from_jqcli_config()
    if not cookie:
        # 登录接口通了但配置里没 cookie：jqcli 研究平台依赖网页 cookie，
        # 拿不到票就绝不能回写 .env（假续票=下游照旧 401）
        print("[失败] 登录返回成功但没拿到 cookie")
        print("       请人工登录网页端复制 Cookie 到 .env 的 JQCLI_COOKIE")
        return False
    _write_env("JQCLI_COOKIE", cookie)
    print(f"[续票] 新 Cookie 已回写 .env（长度 {len(cookie)}）")
    return check()


def ensure() -> bool:
    """供其它模块调用的无参入口：健康返回 True；失效则续票，成也 True。"""
    if check():
        return True
    print("[动作] 会话不可用，尝试自动登录续票…")
    return login()


def main() -> int:
    ap = argparse.ArgumentParser(description="聚宽 Cookie 自动续期")
    ap.add_argument("--force", action="store_true", help="无条件重新登录")
    a = ap.parse_args()

    if not a.force and check():
        print("[健康] 聚宽会话有效，无需续票")
        return 0
    print("[动作] 会话不可用，尝试自动登录续票…" if not a.force
          else "[动作] --force：无条件重新登录")
    if login():
        print("[完成] 取数通道已恢复")
        return 0
    print("[需人工] 自动续票未成功，请按上面提示处理")
    return 1


if __name__ == "__main__":
    sys.exit(main())
