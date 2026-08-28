# -*- coding: utf-8 -*-
"""数据采集层（research 中间区）

覆盖**日线与分钟线**两种粒度：
    1. qlib 全市场日线：初始化/下载本地数据（来自 playground/init_qlib_data.py）
    2. 东财标的 K 线采集：日线(AKShare) + 分钟(东财接口)，标的可参数化

设计要点：
    - 所有对外函数均以 `secid` / `period` / `out` 等为参数，不硬编码具体标的。
    - 统一输出到 data/bt_export/，列名与策略所需对齐。
"""

import os
import shutil
import zipfile
from pathlib import Path

import pandas as pd

from research.config import PROJECT_ROOT, bt_export_dir

# ---------- qlib 日线初始化相关 ----------
QLIB_REQUIRED_DIRS = ["calendars", "features", "instruments"]

# GitHub 加速镜像（国内网络可用），按顺序尝试
MIRROR_PREFIXES = ["https://gh-proxy.com/", "https://ghfast.top/"]

INVESTMENT_DATA_RELEASE_URL_TMPL = (
    "https://github.com/chenditc/investment_data/releases/download/{tag}/{asset}"
)
# 社区日更 A股日线（最新 tag；可通过环境变量覆盖）
INVESTMENT_DATA_TAG = os.getenv("INVESTMENT_DATA_TAG", "2026-08-13")

QLIB_GITHUB_URL_TMPL = "https://github.com/SunsetWolf/qlib_dataset/releases/download/v2/{name}"
QLIB_CANDIDATE_FILES = ["qlib_data_cn_1d_latest.zip"]

DOWNLOAD_TIMEOUT = 1200   # 单次请求超时（秒），大文件需放宽
CHUNK_SIZE = 1024 * 512


# ---------- qlib 全市场日线 ----------
def qlib_data_exists(target: Path) -> bool:
    """判断 target 目录是否已具备标准 qlib 数据布局。"""
    return all((target / d).exists() for d in QLIB_REQUIRED_DIRS)


def resolve_urls(raw_url: str) -> list[str]:
    """将 GitHub 直链转换为候选镜像地址列表（含直连兜底）。"""
    override = os.getenv("QLIB_DATA_URL")
    if override:
        return [override]
    candidates = [prefix + raw_url for prefix in MIRROR_PREFIXES] + [raw_url]
    available = []
    for url in candidates:
        try:
            import requests
            resp = requests.head(url, allow_redirects=True, timeout=15)
            if resp.status_code == 200 and url not in available:
                available.append(url)
        except Exception:  # noqa: BLE001
            pass
    # HEAD 全失败也保留全部候选，交由下载阶段逐个实测
    for url in candidates:
        if url not in available:
            available.append(url)
    return available or [raw_url]


def download_file(urls: list[str], target_path: Path, max_tries: int = 5) -> None:
    """带断点续传地下载，多镜像自动切换重试。"""
    import requests
    from tqdm import tqdm

    resume_bytes = target_path.stat().st_size if target_path.exists() else 0
    last_err = None
    for attempt in range(max_tries):
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
            expected = int(resp.headers.get("content-length", 0)) + (resume_bytes if resume_bytes > 0 else 0)
            if target_path.stat().st_size >= expected:
                return
            raise ConnectionError(f"文件不完整: {target_path.stat().st_size}/{expected}")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"[重试] 下载中断: {str(exc)[:80]}，切换镜像重试...")
            resume_bytes = target_path.stat().st_size if target_path.exists() else 0
    raise RuntimeError(f"多次尝试下载均失败: {last_err}")


def _clean_target(target_dir: Path) -> None:
    """删除目标目录下的旧 qlib 数据。"""
    for d in QLIB_REQUIRED_DIRS + ["features_cache", "dataset_cache"]:
        old = target_dir / d
        if old.exists():
            shutil.rmtree(old)


def _extract_tar_gz(archive: Path, target_dir: Path) -> None:
    """解压 tar.gz 到 target_dir（自动剥离顶层目录）。"""
    import tarfile
    from tqdm import tqdm

    top_levels = {}
    with tarfile.open(str(archive), "r:gz") as tf:
        members = tf.getmembers()
        for m in members:
            parts = m.name.split("/")
            if len(parts) >= 1 and parts[0]:
                top_levels.setdefault(parts[0], set())
                top_levels[parts[0]].add(m.name)

    strip = 0
    if len(top_levels) == 1:
        single = next(iter(top_levels))
        if all(sub in single or any(single in p for p in top_levels[single]) for sub in ("calendars", "features")):
            strip = 1
        elif (target_dir / single).is_dir():
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


def _download_and_extract(target_dir: Path, raw_url: str, asset: str) -> None:
    """下载并解压单个数据源资产。"""
    urls = resolve_urls(raw_url)
    target_dir.mkdir(exist_ok=True, parents=True)
    archive = target_dir / f"tmp_{asset}"
    try:
        download_file(urls, archive)
        _clean_target(target_dir)
        if asset.endswith(".zip"):
            with zipfile.ZipFile(str(archive), "r") as zp:
                from tqdm import tqdm
                for member in tqdm(zp.namelist(), desc="unzipping"):
                    zp.extract(member, str(target_dir))
        else:
            _extract_tar_gz(archive, target_dir)
    finally:
        archive.unlink(missing_ok=True)


def ensure_qlib_data(target_dir: Path | None = None, force: bool = False,
                     source: str = "investment_data") -> bool:
    """确保 qlib 全市场日线数据就绪。

    参数：
        target_dir: qlib 数据目录；缺省用 config.qlib_uri()。
        force:      True 则无视已有数据强制重新下载。
        source:     "investment_data"(社区日更) 或 "qlib_official"(官方旧打包)。
    返回：
        数据是否就绪（具备标准布局）。
    """
    target_dir = Path(target_dir or PROJECT_ROOT / "data" / "cn_data")
    if qlib_data_exists(target_dir) and not force:
        print(f"[跳过] 数据已存在: {target_dir}")
        return True

    if source == "qlib_official":
        name = QLIB_CANDIDATE_FILES[0]
        raw_url = QLIB_GITHUB_URL_TMPL.format(name=name)
        _download_and_extract(target_dir, raw_url, name)
    else:
        asset = "qlib_bin.tar.gz"
        raw_url = INVESTMENT_DATA_RELEASE_URL_TMPL.format(tag=INVESTMENT_DATA_TAG, asset=asset)
        _download_and_extract(target_dir, raw_url, asset)

    ok = qlib_data_exists(target_dir)
    if not ok:
        print("[失败] 数据解压后结构不完整，请检查。")
    return ok


# ---------- 东财标的 K 线采集（分钟 / 日线通用）----------
_EASTMONEY_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"


def fetch_eastmoney_kline(secid: str, period: int = 5,
                          start: str = "20230101", end: str = "20500000",
                          retries: int = 4) -> pd.DataFrame:
    """请求东方财富 kline 接口，返回原始 DataFrame。

    参数：
        secid:  交易所.代码，如 "1.513310"（沪）/"0.159915"（深）。
        period: K 线周期：1/5/15/30/60 为分钟；101=日，102=周，103=月。
    返回列：时间/开盘/收盘/最高/最低/成交量/成交额/振幅/涨跌幅/涨跌额/换手率
    """
    import time

    import requests

    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "klt": period,
        "fqt": "0",
        "secid": secid,
        "beg": start,
        "end": end,
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for attempt in range(retries):
        try:
            r = requests.get(_EASTMONEY_URL, timeout=20, params=params, headers=headers)
            data_json = r.json()
            if not data_json.get("data") or not data_json["data"].get("klines"):
                raise ValueError(f"无数据: {data_json}")
            rows = [item.split(",") for item in data_json["data"]["klines"]]
            return pd.DataFrame(
                rows,
                columns=["时间", "开盘", "收盘", "最高", "最低", "成交量", "成交额",
                         "振幅", "涨跌幅", "涨跌额", "换手率"],
            )
        except Exception as e:  # noqa: BLE001
            print(f"  第{attempt+1}次尝试失败: {e}")
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("多次请求均失败。")


def clean_bars(df: pd.DataFrame, min_bars_per_day: int = 40) -> pd.DataFrame:
    """清洗 K 线数据：转数值、剔除非完整交易日。

    参数：
        df:               fetch_eastmoney_kline / akshare 返回的原始数据。
        min_bars_per_day: 判定"完整交易日"的最少 bar 数（5分钟日线为48）。
    返回列：date/时间/开盘/收盘/最高/最低/成交量/成交额
    """
    df = df.copy()
    num_cols = ["开盘", "收盘", "最高", "最低", "成交量", "成交额"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    # 东财分钟数据有"时间"列；akshare 日线用"日期"。统一成 datetime 索引列。
    if "时间" in df.columns:
        ts = pd.to_datetime(df["时间"])
        df["datetime"] = ts
        df["date"] = ts.dt.date
        # 只剔除未收盘的不完整日（仅对日内多 bar 有意义）
        cnt = df.groupby("date")["datetime"].transform("count")
        df = df[cnt >= min_bars_per_day].copy()
        cols = ["date", "datetime", "开盘", "收盘", "最高", "最低", "成交量", "成交额"]
        return df[cols]
    # 日线（单行/天）：直接对齐列名
    rename_map = {"日期": "date", "开盘": "open", "收盘": "close",
                  "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount"}
    df = df.rename(columns=rename_map)
    keep = [c for c in ["date", "open", "high", "low", "close", "volume", "amount"] if c in df.columns]
    out = df[keep].copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"])
    return out.sort_values("date").reset_index(drop=True)


def _symbol_of(secid: str) -> str:
    """从 secid（如 '1.513310'）提取纯代码。"""
    return secid.split(".")[-1]


def fetch_minute_csv(secid: str, period: int = 5,
                     min_bars: int = 48, start: str = "20230101",
                     end: str = "20500000") -> Path:
    """抓取→清洗→本地化存储标的分钟 K 线。

    默认输出：data/bt_export/{symbol}_{period}min.csv
    """
    symbol = _symbol_of(secid)
    raw = fetch_eastmoney_kline(secid, period=period, start=start, end=end)
    clean = clean_bars(raw, min_bars_per_day=min_bars)
    out = bt_export_dir() / f"{symbol}_{period}min.csv"
    clean.to_csv(out, index=False)
    print(f"已保存 {len(clean)} 行 -> {out}（{clean['date'].nunique()} 个交易日）")
    return out


def fetch_daily_csv(symbol: str, start_date: str = "20200101",
                    end_date: str = "20300101", adjust: str = "") -> Path:
    """抓取→清洗→本地化存储标的日线 K 线（AKShare 东方财富）。

    默认输出：data/bt_export/{symbol}_daily.csv
    adjust="" 表示不复权（纯价差择时回测，避免复权引入未来信息）。
    """
    import akshare as ak

    df = ak.fund_etf_hist_em(
        symbol=symbol, period="daily",
        start_date=start_date, end_date=end_date, adjust=adjust,
    )
    if df is None or df.empty:
        raise RuntimeError(f"未获取到数据: {symbol}")
    clean = clean_bars(df)
    out = bt_export_dir() / f"{symbol}_daily.csv"
    clean.to_csv(out, index=False)
    print(f"已保存 {len(clean)} 行 -> {out}")
    return out
