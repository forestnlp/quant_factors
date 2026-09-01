# -*- coding: utf-8 -*-
"""统一配置读取（research 中间区）

从 .env 与环境变量解析项目关键路径与参数，一处维护，供各模块复用。

主要职责：
    1. 定位项目根目录
    2. 读取 .env 中的 QLIB_URI（qlib 全市场日线目录）
    3. 提供数据产物输出目录 data/bt_export

用法：
    from research.config import PROJECT_ROOT, qlib_uri, bt_export_dir
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _parse_env_file(path: Path) -> dict:
    """解析简易 .env 文件为字典（忽略注释与空行）。"""
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip()
    return env


def load_env() -> dict:
    """返回 .env 内容的字典。环境变量优先于 .env 文件。"""
    parsed = _parse_env_file(PROJECT_ROOT / ".env")
    return {k: os.getenv(k, v) for k, v in parsed.items()}


def qlib_uri() -> Path:
    """返回 qlib 全市场日线数据目录。

    优先级：环境变量 QLIB_URI > .env 的 QLIB_URI > 缺省 data/cn_data。
    """
    env = _parse_env_file(PROJECT_ROOT / ".env")
    raw = os.getenv("QLIB_URI", env.get("QLIB_URI", str(PROJECT_ROOT / "data" / "cn_data")))
    p = Path(raw).expanduser()
    return p if p.is_absolute() else PROJECT_ROOT / p


def bt_export_dir() -> Path:
    """返回数据产物输出目录 data/bt_export（自动创建）。"""
    d = PROJECT_ROOT / "data" / "bt_export"
    d.mkdir(parents=True, exist_ok=True)
    return d


def industry_map_dir() -> Path:
    """返回行业/概念映射数据目录 data/industry_map（自动创建）。"""
    d = PROJECT_ROOT / "data" / "industry_map"
    d.mkdir(parents=True, exist_ok=True)
    return d


def llm_config() -> dict:
    """返回本地大模型 API 配置。

    优先级：环境变量 > .env > 缺省。
    键：
        base_url   OpenAI 兼容接口地址（如 http://host:port/v1）
        api_key    鉴权密钥
        model      模型名
    """
    env = _parse_env_file(PROJECT_ROOT / ".env")
    get = lambda key, default=None: os.getenv(key, env.get(key, default))  # noqa: E731
    return {
        "base_url": get("LLM_BASE_URL", "http://192.168.7.228:18082/v1"),
        "api_key": get("LLM_API_KEY", ""),
        "model": get("LLM_MODEL", "Qwen3.8-Flash"),
    }
