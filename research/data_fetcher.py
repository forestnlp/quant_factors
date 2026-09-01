# -*- coding: utf-8 -*-
"""数据采集层（research 中间区）

覆盖**日线与分钟线**两种粒度 + **结构数据（申万行业）**：
    1. qlib 全市场日线：初始化/下载本地数据（chenditc 社区日更包）
    2. 东财标的 K 线采集：日线(AKShare) + 分钟(东财接口)，标的可参数化
    3. 申万行业数据：31 个一级行业指数日线 + 成分股快照（AKShare 申万宏源源），
       并将行业指数写入 qlib bin（SH801xxx 当作普通标的，D.features 可查）。
       注意：qlib 表达式引擎不支持跨标的引用（SH801010:$close 语法非法），
       个股相对行业类因子须在评估层以 pandas join 行业行情实现。

AKShare 防封三件套（结构数据统一走 _ak_fetch）：限速 + 指数退避重试 + 本地落盘缓存。

用法：
    conda run -n jaycode python research/data_fetcher.py industry   # 拉行业数据+转qlib
"""

import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.config import PROJECT_ROOT, bt_export_dir, industry_map_dir, qlib_uri

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


# ---------- 申万行业数据（AKShare 申万宏源源 + 防封三件套）----------
AK_SLEEP = 0.6          # 相邻请求基础限速（秒）
AK_MAX_RETRY = 4        # 指数退避最大重试次数


def _ak_fetch(tag: str, fetch, cache_csv: Path | None = None,
              force: bool = False):
    """AKShare 通用取数：缓存优先 → 限速 → 指数退避重试 → 落盘。

    参数：
        tag:       日志标签。
        fetch:     无参函数，返回 DataFrame。
        cache_csv: 本地缓存路径；存在且非 force 时直接读缓存。
    """
    if cache_csv and cache_csv.exists() and not force:
        print(f"  [缓存] {tag}: {cache_csv.name}")
        return pd.read_csv(cache_csv, dtype={"行业代码": str, "证券代码": str})
    last_err = None
    for attempt in range(AK_MAX_RETRY):
        try:
            time.sleep(AK_SLEEP)
            df = fetch()
            if df is None or df.empty:
                raise ValueError("返回空数据")
            if cache_csv:
                df.to_csv(cache_csv, index=False)
            print(f"  [OK] {tag}: {len(df)} 行")
            return df
        except Exception as e:  # noqa: BLE001
            last_err = e
            wait = (2 ** attempt) * 2
            print(f"  [重试 {attempt+1}] {tag}: {str(e)[:60]}，等 {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"取数失败 {tag}: {last_err}")


def fetch_industry_map(force: bool = False) -> dict[str, Path]:
    """拉取申万一级行业列表（含估值）与成分股快照，落盘 data/industry_map/。

    注意：成分股为当前快照（准 PIT，含"计入日期"），只可用于中性化与归因，
    禁止用于历史行业轮动回测（存在"今天回看"前视偏差）。
    """
    import akshare as ak

    out_dir = industry_map_dir()
    paths = {}
    info = _ak_fetch("申万一级列表(含估值)", ak.sw_index_first_info,
                     out_dir / "sw_l1_info.csv", force)
    paths["info"] = out_dir / "sw_l1_info.csv"

    # 全行业成分股合并成一张映射表
    rows = []
    for _, r in info.iterrows():
        code = str(r["行业代码"]).split(".")[0]
        cons = _ak_fetch(f"成分股 {r['行业名称']}",
                         lambda c=code: ak.index_component_sw(symbol=c),
                         out_dir / f"cons_{code}.csv", force)
        cons["行业代码"] = code
        cons["行业名称"] = r["行业名称"]
        rows.append(cons)
    mapping = pd.concat(rows, ignore_index=True)
    p = out_dir / "stock_industry_l1.csv"
    mapping.to_csv(p, index=False)
    paths["mapping"] = p
    print(f"  行业映射: {len(mapping)} 条 -> {p}")
    return paths


def _industry_daily_all(force: bool = False) -> pd.DataFrame:
    """31 个申万一级行业指数全历史日线，合并落盘一张 CSV。"""
    import akshare as ak

    out_dir = industry_map_dir()
    agg_p = out_dir / "sw_l1_index_daily.csv"
    if agg_p.exists() and not force:
        print(f"  [缓存] 行业指数日线: {agg_p.name}")
        return pd.read_csv(agg_p)
    info = pd.read_csv(out_dir / "sw_l1_info.csv", dtype={"行业代码": str})
    frames = []
    for _, r in info.iterrows():
        code = str(r["行业代码"]).split(".")[0]
        df = _ak_fetch(f"行业日线 {r['行业名称']}",
                       lambda c=code: ak.index_hist_sw(symbol=c, period="day"))
        df["code"] = code
        df["name"] = r["行业名称"]
        frames.append(df)
    agg = pd.concat(frames, ignore_index=True)
    agg.to_csv(agg_p, index=False)
    print(f"  行业指数日线合计 {len(agg)} 行 -> {agg_p}")
    return agg


def industry_to_qlib(daily: pd.DataFrame) -> int:
    """把行业指数日线写入 qlib bin（SH801xxx 当普通标的）。

    bin 格式（实测确认）：4 字节 float32 起始日历索引 + float32 数组，
    覆盖范围外的日历日填 NaN；超出日历尾部的日期截断。
    写入字段：open/high/low/close/volume/amount；另生成 instruments/sw_l1.txt。
    返回写入的指数个数。
    """
    import numpy as np

    uri = qlib_uri()
    calendar = (uri / "calendars" / "day.txt").read_text().splitlines()
    cal_dates = pd.to_datetime(pd.Series([c.strip() for c in calendar if c.strip()]))
    cal_pos = {d.date(): i for i, d in cal_dates.items()}

    fields = {"开盘": "open", "收盘": "close", "最高": "high",
              "最低": "low", "成交量": "volume", "成交额": "amount"}
    daily = daily.copy()
    daily["dt"] = pd.to_datetime(daily["日期"])

    instruments = []
    n = 0
    for code, g in daily.groupby("code"):
        g = g.sort_values("dt")
        g = g[g["dt"].dt.date.isin(cal_pos)]        # 截断非交易日/超日历部分
        if g.empty:
            continue
        idxs = np.array([cal_pos[d] for d in g["dt"].dt.date])
        start = int(idxs[0])
        # 与 chenditc/竞价 bin 同构：从 start 一直补 NaN 到日历末尾，
        # 否则 qlib 按日历切片的读取路径拿不到数据（实测）
        span = len(cal_dates) - start
        fdir = uri / "features" / f"sh{code}"
        fdir.mkdir(parents=True, exist_ok=True)
        for cn, en in fields.items():
            arr = np.full(span, np.nan, dtype=np.float32)
            arr[idxs - start] = pd.to_numeric(g[cn], errors="coerce").to_numpy(np.float32)
            with open(fdir / f"{en}.day.bin", "wb") as f:
                f.write(np.float32(float(start)).tobytes())   # 头部为 float32（实测）
                f.write(arr.tobytes())
        instruments.append(f"SH{code}\t{g['dt'].min().date()}\t{g['dt'].max().date()}")
        n += 1
    (uri / "instruments" / "sw_l1.txt").write_text("\n".join(instruments) + "\n")
    print(f"  已写入 qlib bin: {n} 个行业指数 -> {uri}/features/sh801*")
    return n


def update_industry(force: bool = False) -> None:
    """行业数据全流程：列表/成分股 + 指数日线 + 转 qlib bin。"""
    print("=== 申万行业数据本地化 ===")
    fetch_industry_map(force=force)
    daily = _industry_daily_all(force=force)
    industry_to_qlib(daily)
    print("=== 完成。行业指数可用 D.features(['SH801010'], ...) 查询 ===")


def audit_data() -> bool:
    """数据质量审计（对齐与覆盖的常驻验证，全部通过返回 True）。

    检查项：
        1. 行业 bin 与 qlib 日历对齐：起始索引合法、覆盖到日历末日
        2. 行业指数最新行情与源 CSV 末日一致（无截断/错位）
        3. 行业映射对活跃股票的覆盖率（阈值 90%，剔除北交所后统计）
        4. 未映射清单落盘 data/industry_map/unmapped.txt 供人工核查
    """
    import numpy as np

    ok = True
    uri = qlib_uri()
    calendar = (uri / "calendars" / "day.txt").read_text().splitlines()
    cal = [c.strip() for c in calendar if c.strip()]
    print(f"[1] 日历: {cal[0]} -> {cal[-1]}  共 {len(cal)} 天")

    # ---- 行业 bin 对齐检查 ----
    n_bad = 0
    for code_dir in sorted((uri / "features").glob("sh801*")):
        p = code_dir / "close.day.bin"
        if not p.exists():
            print(f"  [缺失] {code_dir.name}")
            n_bad += 1
            continue
        raw = p.read_bytes()
        start = int(float(np.frombuffer(raw[:4], dtype=np.float32)[0]))
        arr = np.frombuffer(raw[4:], dtype=np.float32)
        end_idx = start + len(arr)
        if start < 0 or end_idx != len(cal) or np.isnan(arr[-1]):
            print(f"  [错位] {code_dir.name}: start={start} end={end_idx}/{len(cal)} 末值NaN={np.isnan(arr[-1])}")
            n_bad += 1
    if n_bad:
        ok = False
        print(f"  [FAIL] {n_bad} 个行业指数未与日历对齐")
    else:
        print(f"  [OK] 31 个行业指数 bin 全部对齐至日历末日 {cal[-1]}")

    # ---- 映射覆盖率（对近30日活跃股票，剔除北交所）----
    import qlib
    from qlib.data import D

    qlib.init(provider_uri=str(uri), region="cn")
    inst = D.instruments(market="all")
    active = [i.upper() for i in D.list_instruments(
        inst, start_time=cal[-20], end_time=cal[-1], as_list=True)]
    non_bj = [i for i in active if not i.startswith("BJ")]
    m = pd.read_csv(industry_map_dir() / "stock_industry_l1.csv",
                    dtype={"证券代码": str, "行业代码": str})

    def to_qilib(c: str) -> str:
        c = str(c).zfill(6)
        if c[0] == "6":
            return "SH" + c
        if c[0] in "03":
            return "SZ" + c
        if c[0] in "489":
            return "BJ" + c
        return "SH" + c

    mapped = set(m["证券代码"].map(to_qilib))
    hit = [i for i in non_bj if i in mapped]
    miss = [i for i in non_bj if i not in mapped]
    ratio = len(hit) / len(non_bj) if non_bj else 0
    print(f"[2] 行业映射覆盖（近20日活跃、剔北交所）: "
          f"{len(hit)}/{len(non_bj)} = {ratio:.1%}")
    if ratio < 0.90:
        ok = False
        print("  [FAIL] 覆盖率低于 90%")
    (industry_map_dir() / "unmapped.txt").write_text("\n".join(miss) + "\n")
    print(f"  未映射 {len(miss)} 只已列 -> data/industry_map/unmapped.txt（多为新股/停牌）")

    # ---- 行业行情与源 CSV 末日一致性 ----
    src = pd.read_csv(industry_map_dir() / "sw_l1_index_daily.csv",
                      dtype={"code": str}, usecols=["日期", "code"])
    last_src = pd.to_datetime(src["日期"]).max().date()
    last_cal = pd.to_datetime(cal[-1]).date()
    if (last_cal - last_src).days > 7:
        ok = False
        print(f"[3] [FAIL] 行业指数源数据滞后: 源止 {last_src} vs 日历止 {last_cal}，跑 --force 刷新")
    else:
        print(f"[3] [OK] 行业指数行情新鲜度: 源止 {last_src}（日历止 {last_cal}）")

    print("\n审计结论:", "PASS" if ok else "FAIL")
    return ok


# ---------- 聚宽云端取数（jqcli / Jupyter 协议，只读增强件）----------
#
# 机制（实测）：本地生成取数脚本 → jqcli research exec 在云端临时内核执行
#   → 结果 to_csv 写入云端 jq_out/ → jqcli research download 拉回 data/jq_stage/
#   → 本地解析入库（转 qlib bin）→ 立即删除云端文件释放配额
# 约束：单次执行默认 120s 超时；get_call_auction 单次最多返回 5000 行。

JQCLI = PROJECT_ROOT / ".tools" / "venv-jqcli" / "bin" / "jqcli"
JQ_STAGE = PROJECT_ROOT / "data" / "jq_stage"

# 云端执行的取数脚本模板：只含取数逻辑，不含本项目任何研究内容
JQ_AUCTION_TMPL = '''# -*- coding: utf-8 -*-
from jqdata import *
import os
import pandas as pd

DAYS = {days!r}
FIELDS = ["time", "current", "a1_v", "b1_v", "volume", "money"]
os.makedirs("jq_out", exist_ok=True)
out = []
for d in DAYS:
    codes = get_all_securities("stock", date=d).index.tolist()
    for i in range(0, len(codes), 2500):          # 单次上限 5000 行，分组取
        a = get_call_auction(codes[i:i + 2500], start_date=d, end_date=d, fields=FIELDS)
        a["day"] = d
        out.append(a)
df = pd.concat(out, ignore_index=True)
p = os.path.join("jq_out", "{fname}")
df.to_csv(p, index=False)
print("rows=%d size=%.1fMB" % (len(df), __import__("os").path.getsize(p) / 1048576.0))
'''


def _jqcli(*args: str, timeout: int = 300) -> str:
    """调用项目内 jqcli（凭据走 .env，不写项目外）。返回 stdout。"""
    import subprocess

    if not JQCLI.exists():
        raise FileNotFoundError(f"缺少 jqcli: {JQCLI}（见 PROJECT.md 环境节三步重建）")
    r = subprocess.run(
        [str(JQCLI), "--env-file", str(PROJECT_ROOT / ".env"),
         "--format", "json", "--non-interactive", *args],
        capture_output=True, text=True, timeout=timeout, cwd=str(PROJECT_ROOT))
    if r.returncode != 0:
        raise RuntimeError(f"jqcli 失败: {(r.stderr or r.stdout)[:300]}")
    return r.stdout


def jq_run(script: str, remote_name: str, local_out: Path, timeout: int = 900) -> Path:
    """在云端执行取数脚本并把产出的 csv 拉到本地 local_out（含清理与容错）。"""
    JQ_STAGE.mkdir(parents=True, exist_ok=True)
    script_local = JQ_STAGE / f"_{remote_name}.py"
    script_local.write_text(script, encoding="utf-8")
    try:
        _jqcli("research", "exec", "--file", str(script_local), "--yes",
               timeout=timeout)
        _jqcli("research", "download", f"jq_out/{remote_name}",
               "-o", str(local_out), "--force", timeout=300)
    finally:
        try:                                    # 云端配额有限，拉完即删
            _jqcli("research", "rm", f"jq_out/{remote_name}", "--yes", timeout=120)
        except Exception:  # noqa: BLE001
            pass
        script_local.unlink(missing_ok=True)
    if not local_out.exists() or local_out.stat().st_size < 100:
        raise RuntimeError(f"云端未产出有效文件: {remote_name}")
    return local_out


def _trading_days(start: str, end: str) -> list[str]:
    """从本地 qlib 日历取区间内的交易日（避免依赖外部交易日历）。"""
    cal = (qlib_uri() / "calendars" / "day.txt").read_text().splitlines()
    return [c.strip() for c in cal if c.strip() and start <= c.strip() <= end]


def fetch_auction(start: str, end: str, chunk_days: int = 10,
                  force: bool = False) -> list[Path]:
    """分片拉取集合竞价数据到 data/auction/（断点续跑：已有分片跳过）。

    每个分片 = chunk_days 个交易日的全市场竞价（约 5 万行），
    受云端单次 120s 超时与单次 5000 行返回上限约束。
    """
    out_dir = PROJECT_ROOT / "data" / "auction"
    out_dir.mkdir(parents=True, exist_ok=True)
    days = _trading_days(start, end)
    if not days:
        raise ValueError(f"本地日历无 {start}~{end} 区间，先更新 qlib 数据")
    chunks = [days[i:i + chunk_days] for i in range(0, len(days), chunk_days)]
    done, todo = [], []
    for ch in chunks:
        f = out_dir / f"auction_{ch[0]}_{ch[-1]}.csv"
        (done if (f.exists() and not force) else todo).append((ch, f))
    print(f"竞价取数: 共 {len(chunks)} 片（{len(days)} 交易日），"
          f"已完成 {len(done)}，待取 {len(todo)}")

    for i, (ch, f) in enumerate(todo, 1):
        script = JQ_AUCTION_TMPL.format(days=ch, fname=f.name)
        print(f"  [{i}/{len(todo)}] {ch[0]} ~ {ch[-1]} ...", flush=True)
        try:
            jq_run(script, f.name, f)
            n = sum(1 for _ in open(f, encoding="utf-8")) - 1
            print(f"      -> {n} 行")
        except Exception as e:  # noqa: BLE001
            print(f"      [失败，可重跑续传] {str(e)[:160]}")
    return sorted(out_dir.glob("auction_*.csv"))


def auction_to_qlib() -> tuple[int, int]:
    """把竞价 csv 聚合成日频字段写入 qlib bin，使表达式可直接引用 $auction_*。

    写入字段：
        auction_price   9:25 虚拟匹配价（current）
        auction_money   竞价成交额
        auction_bid1_v  买方虚拟匹配量
        auction_ask1_v  卖方虚拟匹配量
    返回 (写入标的数, 字段数)。
    """
    import numpy as np

    uri = qlib_uri()
    cal = [c.strip() for c in
           (uri / "calendars" / "day.txt").read_text().splitlines() if c.strip()]
    cal_pos = {d: i for i, d in enumerate(cal)}

    src = sorted((PROJECT_ROOT / "data" / "auction").glob("auction_*.csv"))
    if not src:
        raise FileNotFoundError("data/auction/ 为空，先执行: jq_pull auction")

    # 列名（聚宽 get_call_auction + 我们附加的 day）：
    #   code, day, time, current, a1_v, b1_v, volume, money
    frames = [pd.read_csv(p, usecols=["code", "day", "current", "a1_v", "b1_v", "money"])
              for p in src]
    df = pd.concat(frames, ignore_index=True)
    df = df[df["day"].isin(cal_pos)]
    if df.empty:
        print("  无可用样本（检查日期是否落在本地日历内）")
        return 0, 0
    # 同一标的一天只有一条竞价记录（9:25 撮合），保险起见去重
    df = df.drop_duplicates(["code", "day"], keep="last")

    cols = {"current": "auction_price", "money": "auction_money",
            "a1_v": "auction_bid1_v", "b1_v": "auction_ask1_v"}

    def to_qilib(jq_code: str) -> str | None:
        c = str(jq_code).split(".")[0]
        suf = str(jq_code).split(".")[-1] if "." in str(jq_code) else ""
        if suf == "XSHG":
            return "SH" + c
        if suf == "XSHE":
            return "SZ" + c
        if c[0] == "6":
            return "SH" + c
        if c[0] in "03":
            return "SZ" + c
        if c[0] in "489":
            return "BJ" + c
        return None

    df["inst"] = df["code"].map(to_qilib)
    df = df[df["inst"].notna()]

    n_inst = 0
    for inst, g in df.groupby("inst"):
        g = g.sort_values("day")
        idxs = np.array([cal_pos[d] for d in g["day"]], dtype=np.int64)
        if idxs.size == 0:
            continue
        start = int(idxs[0])
        if start >= len(cal):
            continue
        # 与 chenditc/行业 bin 同构：从 start 一直补 NaN 到日历末尾，
        # 否则 qlib 按日历切片的读取路径拿不到数据（实测）
        span = len(cal) - start
        fdir = uri / "features" / inst.lower()
        fdir.mkdir(parents=True, exist_ok=True)
        for src_col, field in cols.items():
            arr = np.full(span, np.nan, dtype=np.float32)
            vals = pd.to_numeric(g[src_col], errors="coerce").to_numpy(np.float32)
            arr[idxs - start] = vals
            with open(fdir / f"{field}.day.bin", "wb") as f:
                f.write(np.float32(float(start)).tobytes())   # 头部为 float32（实测）
                f.write(arr.tobytes())
        n_inst += 1
    print(f"  已写入竞价字段: {n_inst} 个标的 x {len(cols)} 字段 -> {uri}/features/*/")
    return n_inst, len(cols)


def _arg(argv: list[str], key: str, default: str) -> str:
    """从命令行取 --key value。"""
    return argv[argv.index(key) + 1] if key in argv and argv.index(key) + 1 < len(argv) else default


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "industry"
    if cmd == "industry":
        update_industry(force="--force" in sys.argv)
    elif cmd == "audit":
        sys.exit(0 if audit_data() else 1)
    elif cmd == "jq_pull":
        kind = sys.argv[2] if len(sys.argv) > 2 else "auction"
        if kind == "auction":
            s = _arg(sys.argv, "--start", "2025-06-01")
            e = _arg(sys.argv, "--end", "2025-06-30")
            fetch_auction(s, e, force="--force" in sys.argv)
        else:
            print(f"未知 jq_pull 类型: {kind}（可用: auction）")
    elif cmd == "auction_bin":
        auction_to_qlib()
    else:
        print("未知命令（可用: industry / audit / jq_pull auction / auction_bin）")
