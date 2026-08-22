# -*- coding: utf-8 -*-
"""Qlib A股日线数据初始化脚本（实验区）

功能：
    1. 从 .env 的 QLIB_URI 读取目标数据目录（缺省回退项目根 data/cn_data）
    2. 若目标已有标准 qlib 数据（calendars/features/instruments）则跳过
    3. 否则从数据源自动下载并解压到目标目录（整体替换）

数据源（按优先级）：
    - 社区维护、每日更新的 A股日线（chenditc/investment_data，含近年行情，
      最新可至 2026+）：https://github.com/chenditc/investment_data
      release 资产 qlib_bin.tar.gz / qlib_bin.manifest.json
    - qlib 官方打包（microsoft/SunsetWolf 镜像，仅更新到 2020-09）

用法：
    conda run -n jaycode python playground/init_qlib_data.py
    # 强制重新下载（覆盖已有数据）
    conda run -n jaycode python playground/init_qlib_data.py --force

成功标准：
    脚本无异常退出，目标数据目录下生成 calendars / features / instruments 三个子目录。
"""

import os
import shutil
import sys
import zipfile
from pathlib import Path

import requests
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ---------- 读取 .env 配置 ----------
_env = {}
if (PROJECT_ROOT / ".env").exists():
    for line in (PROJECT_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        _env[key.strip()] = val.strip()

QLIB_URI = Path(os.getenv("QLIB_URI", _env.get("QLIB_URI", str(PROJECT_ROOT / "data" / "cn_data")))).expanduser()

# ---------- 数据源定义 ----------
# GitHub 加速镜像（国内网络可用），按顺序尝试
MIRROR_PREFIXES = [
    "https://gh-proxy.com/",
    "https://ghfast.top/",
]

# 主数据源：chenditc/investment_data（社区日更，含近年行情）
INVESTMENT_DATA_RELEASE_URL_TMPL = (
    "https://github.com/chenditc/investment_data/releases/download/{tag}/{asset}"
)
# 使用具体日期 tag（latest 链接不稳定且 GET 可能 404）；可随时改到更新的日期
INVESTMENT_DATA_TAG = os.getenv("INVESTMENT_DATA_TAG", "2026-08-13")

# 备选数据源：qlib 官方打包（仅到 2020-09）
QLIB_GITHUB_URL_TMPL = "https://github.com/SunsetWolf/qlib_dataset/releases/download/v2/{name}"
QLIB_CANDIDATE_FILES = ["qlib_data_cn_1d_latest.zip"]

DOWNLOAD_TIMEOUT = 1200   # 单次请求超时（秒），大文件需放宽
CHUNK_SIZE = 1024 * 512


def data_exists(target: Path) -> bool:
    """判断目标目录是否已具备标准 qlib 数据布局。"""
    required = ["calendars", "features", "instruments"]
    return all((target / d).exists() for d in required)


def resolve_urls(raw_url: str) -> list[str]:
    """将 GitHub 直链转换为候选镜像地址列表（含直连兜底）。

    优先使用环境变量 QLIB_DATA_URL 指定的完整直链。
    无论 HEAD 探测结果如何，都返回全部候选，交由下载阶段逐个实测。
    """
    override = os.getenv("QLIB_DATA_URL")
    if override:
        return [override]
    candidates = [prefix + raw_url for prefix in MIRROR_PREFIXES] + [raw_url]
    available = []
    for url in candidates:
        try:
            resp = requests.head(url, allow_redirects=True, timeout=15)
            if resp.status_code == 200 and url not in available:
                available.append(url)
        except requests.RequestException:
            pass
    # 即使 HEAD 全失败，也保留全部候选，避免误判为不可用
    for url in candidates:
        if url not in available:
            available.append(url)
    return available or [raw_url]


def download_file(urls: list[str], target_path: Path, max_tries: int = 5) -> None:
    """带断点续传地下载，多镜像自动切换重试。"""
    resume_bytes = target_path.stat().st_size if target_path.exists() else 0

    last_err = None
    for attempt in range(max_tries):
        # 当前尝试的镜像按顺序轮换
        url = urls[attempt % len(urls)] if urls else ""
        print(f"\n[下载] {url}（已有 {resume_bytes / 1024**2:.1f} MB，第 {attempt+1} 次）")
        headers = {"Range": f"bytes={resume_bytes}-"} if resume_bytes > 0 else {}
        try:
            with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT, headers=headers) as resp:
                if resume_bytes > 0 and resp.status_code != 206:
                    resume_bytes = 0
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0)) + (resume_bytes if resume_bytes > 0 else 0)
                mode = "ab" if resume_bytes > 0 else "wb"
                with tqdm(total=total, unit="B", unit_scale=True, desc="downloading", initial=resume_bytes) as p_bar:
                    with target_path.open(mode) as fp:
                        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                            if not chunk:
                                continue
                            fp.write(chunk)
                            p_bar.update(len(chunk))
            # 校验文件大小是否达到预期
            expected = int(resp.headers.get("content-length", 0)) + (resume_bytes if resume_bytes > 0 else 0)
            if target_path.stat().st_size >= expected:
                return
            raise ConnectionError(f"文件不完整: {target_path.stat().st_size}/{expected}")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"[重试] 下载中断: {str(exc)[:80]}，切换镜像重试...")
            resume_bytes = target_path.stat().st_size if target_path.exists() else 0
    raise RuntimeError(f"多次尝试下载均失败: {last_err}")


def clean_target(target_dir: Path) -> None:
    """删除目标目录下的旧 qlib 数据。"""
    for d in ("calendars", "features", "instruments", "features_cache", "dataset_cache"):
        old = target_dir / d
        if old.exists():
            print(f"[清理] 删除旧目录: {old}")
            shutil.rmtree(old)


def extract_tar_gz(archive: Path, target_dir: Path) -> None:
    """解压 tar.gz 到 target_dir（自动剥掉顶层目录）。"""
    import tarfile

    # 探测顶层结构，确定剥离层级
    top_levels = {}
    with tarfile.open(str(archive), "r:gz") as tf:
        members = tf.getmembers()
        for m in members:
            parts = m.name.split("/")
            if len(parts) >= 1 and parts[0]:
                top_levels.setdefault(parts[0], set())
                top_levels[parts[0]].add(m.name)

    # 若 tar 内是单个顶层目录（如 cn_data/），需 strip 一层
    strip = 0
    if len(top_levels) == 1:
        single = next(iter(top_levels))
        # 单顶层目录且包含 qlib 子目录
        if all(sub in single or any(single in p for p in top_levels[single]) for sub in ("calendars", "features")):
            strip = 1
        elif os.path.isdir(target_dir / single):
            strip = 1

    print(f"\n[解压] {archive} -> {target_dir}（strip={strip}）")
    target_dir.mkdir(exist_ok=True, parents=True)
    with tarfile.open(str(archive), "r:gz") as tf:
        for member in tqdm(tf.getmembers(), desc="extracting"):
            if not member.isfile():
                continue
            name_parts = member.name.split("/")
            rel_parts = name_parts[strip:] if strip else name_parts
            rel_path = "/".join(rel_parts).strip()
            if not rel_path:
                continue
            dest = target_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            with dest.open("wb") as f:
                shutil.copyfileobj(src, f)


def extract_zip(archive: Path, target_dir: Path) -> None:
    """解压 zip 到 target_dir。"""
    print(f"\n[解压] {archive} -> {target_dir}")
    target_dir.mkdir(exist_ok=True, parents=True)
    with zipfile.ZipFile(str(archive), "r") as zp:
        for member in tqdm(zp.namelist(), desc="unzipping"):
            zp.extract(member, str(target_dir))


def download_investment_data(target_dir: Path) -> None:
    """从 chenditc/investment_data 下载最新 A股日线并解压。"""
    tag = INVESTMENT_DATA_TAG
    asset = "qlib_bin.tar.gz"
    raw_url = INVESTMENT_DATA_RELEASE_URL_TMPL.format(tag=tag, asset=asset)
    urls = resolve_urls(raw_url)

    target_dir.mkdir(exist_ok=True, parents=True)
    archive = target_dir / f"tmp_{asset}"

    try:
        download_file(urls, archive)
        clean_target(target_dir)
        extract_tar_gz(archive, target_dir)
    finally:
        archive.unlink(missing_ok=True)


def download_qlib_official(target_dir: Path) -> None:
    """从 qlib 官方打包下载（备选，仅到 2020-09）。"""
    name = QLIB_CANDIDATE_FILES[0]
    raw_url = QLIB_GITHUB_URL_TMPL.format(name=name)
    urls = resolve_urls(raw_url)

    target_dir.mkdir(exist_ok=True, parents=True)
    archive = target_dir / f"tmp_{name}"
    try:
        download_file(urls, archive)
        clean_target(target_dir)
        extract_zip(archive, target_dir)
    finally:
        archive.unlink(missing_ok=True)


def main() -> None:
    force = "--force" in sys.argv
    print(f"目标数据目录: {QLIB_URI}")

    if data_exists(QLIB_URI) and not force:
        print("[跳过] 数据已存在。如需重新下载请加 --force 参数。")
        return

    source = os.getenv("DATA_SOURCE", "investment_data")
    if source == "investment_data":
        download_investment_data(QLIB_URI)
    else:
        download_qlib_official(QLIB_URI)

    if not data_exists(QLIB_URI):
        print("[失败] 数据解压后结构不完整，请检查。")
        sys.exit(1)

    print("\n[完成] A股日线数据初始化成功：")
    for d in ("calendars", "features", "instruments"):
        print(f"  - {QLIB_URI / d}")


if __name__ == "__main__":
    main()
