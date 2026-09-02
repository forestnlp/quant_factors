# -*- coding: utf-8 -*-
"""统一配置读取

集中维护路径常量；`.env` 由各消费方自行读取（jqcli 走 `--env-file`，
LLM 客户端走环境变量）。约定：

- 原始数据一律落 `data/raw/`（CSV，按来源与粒度分目录），可再生但取回成本高，长期保留。
- 派生数据落 `data/derived/`，随时可由 raw 重建。
- 任何产物不得写到项目目录之外（见 rules.md R4-7/8）。

用法：
    from research.config import PROJECT_ROOT, raw_dir, derived_dir
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"


def raw_dir(*parts: str) -> Path:
    """原始数据目录 data/raw/<parts...>（自动创建）。"""
    d = DATA_ROOT.joinpath("raw", *parts)
    d.mkdir(parents=True, exist_ok=True)
    return d


def derived_dir(*parts: str) -> Path:
    """派生数据目录 data/derived/<parts...>（自动创建）。"""
    d = DATA_ROOT.joinpath("derived", *parts)
    d.mkdir(parents=True, exist_ok=True)
    return d


def jqcli_bin() -> Path:
    """jqcli 可执行文件路径。

    jqcli 源码 vendored 于 `.tools/jqcli`（gitignore），以
    `pip install -e .tools/jqcli` 装入 conda `jaycode` 环境（单一环境，无独立 venv）。
    优先取当前解释器同目录的 jqcli，保证与本进程同环境。
    """
    import shutil
    import sys

    cand = Path(sys.executable).parent / "jqcli"
    if cand.exists():
        return cand
    found = shutil.which("jqcli")
    if found:
        return Path(found)
    raise FileNotFoundError(
        "jqcli 不可用，重建: git clone --depth 1 "
        "https://github.com/breakhearts/jqcli .tools/jqcli && "
        "conda run -n jaycode pip install -e .tools/jqcli")
