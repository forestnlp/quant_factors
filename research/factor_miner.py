# -*- coding: utf-8 -*-
"""本地大模型驱动的因子挖掘闭环（research 中间区）

Phase1 单轮链路（mine）+ Phase2 闭环迭代（loop）：

    Prompt → LLM 生成因子 → 规范化去重 → Qlib 批量评估（全样本 / IS / OOS
    × 原始 / 行业中性）→ 相关性去重 → 全部落因子库 → 失败案例回喂下一轮

loop 的关键设计（对应"闭环负反馈 + 分层过滤防过拟合"）：
    - 有记忆：所有因子（含失败、重复）一律入库，可统计非法率/同质化率/合格率
    - 能筛真货：样本外(OOS) + 行业中性后的 RankICIR 才算过关
    - 防同质：表达式规范化精确去重 + 与库内高分因子的截面相关去重
    - 可断点：表达式唯一约束，重复运行不会二次入库；分批评估，中断可续

用法：
    conda run -n jaycode python research/factor_miner.py mine -n 3   # 单轮
    conda run -n jaycode python research/factor_miner.py loop -b 20   # 闭环迭代 20 批
    conda run -n jaycode python research/factor_miner.py seed         # 导入已验证因子做种子
    conda run -n jaycode python research/factor_miner.py stats        # 查看库统计
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from research.factor_eval import (  # noqa: E402
    add_industry_columns, evaluate_factor, industry_neutral,
    load_factor_data, split_is_oos, winsorize_zscore,
)
from research.factor_lib import VALID_RANKICIR, FactorLib, normalize_expr  # noqa: E402
from research.llm_client import LLMClient  # noqa: E402

# ---------- Qlib 可用字段与表达式规范（注入 prompt）----------
AVAILABLE_FIELDS = "$open $high $low $close $vwap $volume $amount"

EXPR_RULES = (
    "只允许使用以下 qlib 算子（实测可用）："
    "Ref($x,k) 引用第 k 日前；Mean/Std/Sum/Max/Min(x,n) 滚动窗口；"
    "Corr(x,y,n)/Cov 相关系数；Log/Exp/Abs；EMA($x,n)。"
    "禁止 Ref($x,-k) 取未来数据（未来函数）、禁止引入未知字段、禁止除数为零。"
    "注意：qlib 不支持一元负号（如 -Corr(...) 会报错），取反请写 (0 - X) 或 X * -1。"
)

# 历史失败案例兜底（库为空时也用；库里有记录时会追加 recent_failures）
BASE_FAILURES = [
    "Rank(x,1) 等带条件的 Rank 不被支持",
    "跨标的引用（如 SH801010:$close）不被支持",
    "IF/Where 等未列出的算子不被支持",
    "一元负号（如 -Corr(...)、-$close/$vwap）不被支持，取反写 (0 - X) 或 X * -1",
]

# 已验证有效的种子因子（历史手工扫描/LLM 挖掘结论，用于相关性去重的参照系）
SEED_FACTORS = [
    {"name": "turnover_ratio_5", "expr": "Mean($amount,5)/Mean($amount,60)",
     "logic": "量能比：近期成交额相对长期均值的倍数（放量→未来收益偏低，负向）"},
    {"name": "amt_trend", "expr": "Mean($amount,5)/Mean($amount,20)-1",
     "logic": "成交额趋势：短期量能相对中期的抬升幅度"},
    {"name": "mom_20", "expr": "$close/Ref($close,20)-1",
     "logic": "20 日价格动量"},
    {"name": "vol_20", "expr": "Std($close/Ref($close,1)-1,20)",
     "logic": "20 日已实现波动率（高波动→未来收益偏低）"},
    {"name": "vwap_pressure", "expr": "$close/$vwap-1",
     "logic": "收盘相对日内 VWAP 的位置（收盘弱势=日内派发压力）"},
    {"name": "vol_price_corr", "expr": "0 - Corr($close,$volume,10)",
     "logic": "量价相关性反向：上涨无量/下跌放量则趋势难续"},
]

SYSTEM_PROMPT = f"""你是一名资深量化因子研究员，为 A 股全市场横截面选股设计**日线量价因子**。
本地 Qlib 数据集仅含以下字段：{AVAILABLE_FIELDS}。

{EXPR_RULES}

你必须严格输出一个 JSON 对象，不要任何解释文字、不要 markdown 代码块。格式：
{{"name":"因子名(英文字母下划线)","expr":"Qlib表达式","logic":"一句话逻辑假设"}}

要求：因子需有明确的金融逻辑假设；表达式可被 Qlib 解析；
必须与下方"已有因子"在逻辑维度上不同族（不要只改窗口参数或换个符号）。
"""


def build_user_prompt(failures: list[str], logics: list[str]) -> str:
    """构造本轮挖掘指令，注入历史失败案例与已有因子逻辑（负反馈 + 防同族）。"""
    parts = [
        "请提出 1 个全新的、有独立逻辑的 A 股量价日线因子。"
        "已知有效方向偏『负向』（放量/高波动后收益偏低），"
        "可探索：成交量结构、量价背离、波动率聚簇、开盘/收盘相对位置、"
        "成交密集度、日内高低点位置、量能突变等维度。",
    ]
    all_fail = BASE_FAILURES + [f for f in failures if f not in BASE_FAILURES]
    parts.append("历史失败案例（务必避开这些写法）：\n- " + "\n- ".join(all_fail[:14]))
    if logics:
        parts.append("已有因子逻辑（不要与之同族，要探索新维度）：\n- "
                     + "\n- ".join(logics[:20]))
    parts.append("直接输出一个 JSON 对象。")
    return "\n\n".join(parts)


def parse_factor_json(text: str) -> dict:
    """从模型输出中抽取并解析单个因子 JSON。"""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"输出不含 JSON 对象: {text[:200]!r}")
    obj = json.loads(cleaned[start:end + 1])
    name = str(obj.get("name", "")).strip()
    expr = str(obj.get("expr", "")).strip()
    logic = str(obj.get("logic", "")).strip() or ""
    if not name or not expr:
        raise ValueError(f"缺 name 或 expr: {obj}")
    return {"name": name, "expr": expr, "logic": logic}


def generate_factor(client: LLMClient, user_prompt: str) -> dict:
    """调用本地大模型生成一个候选因子定义，解析失败时喂回错误重试一次。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    for attempt in (1, 2):
        text = client.chat(messages, temperature=0.8, max_tokens=16384)
        try:
            return parse_factor_json(text)
        except Exception as e:  # noqa: BLE001
            err = str(e)[:300]
            print(f"[第{attempt}次解析失败] {err}")
            if attempt == 1:
                messages.append({"role": "user",
                                 "content": "你的输出解析失败，错误：" + err +
                                            "\n请重新严格输出单个 JSON 对象。"})
    raise RuntimeError("重试后仍失败")


METRIC_KEYS = ["IC_mean", "ICIR", "RankIC_mean", "RankICIR", "IC_positive_ratio"]


def _sample_days(df, max_days: int = 120):
    """按日期抽样（确定性），用于快速算截面相关性。"""
    import numpy as np

    days = df.index.get_level_values("datetime").unique()
    if len(days) <= max_days:
        return df
    step = int(np.ceil(len(days) / max_days))
    keep = set(days[::step])
    return df[df.index.get_level_values("datetime").isin(keep)]


def evaluate_segments(df, names: list[str], split: str) -> dict[str, dict]:
    """对每个因子输出 全样本 / IS / OOS × 原始 / 行业中性 六套指标。

    返回 {name: {"full": {...}, "is": {...}, "oos": {...},
                "full_neu"/"is_neu"/"oos_neu": {...}, "error": str|None}}
    """
    is_df, oos_df = split_is_oos(df, split)
    segments = {"full": df, "is": is_df, "oos": oos_df}
    has_ind = "_ind" in df.columns
    out = {n: {} for n in names}
    for seg, sub in segments.items():
        if len(sub) == 0:
            continue
        for n in names:
            try:
                out[n][seg] = evaluate_factor(sub, n).to_dict()
                if has_ind:
                    out[n][seg + "_neu"] = evaluate_factor(sub, n + "_neu").to_dict()
            except Exception as e:  # noqa: BLE001
                out[n]["error"] = str(e)[:160]
    return out


def max_corr_with_refs(df, names: list[str], refs: list[str]) -> dict[str, tuple]:
    """新因子与参照因子的最大截面相关（抽样日、皮尔逊），用于同质化判定。"""
    if not refs:
        return {}
    sub = _sample_days(df, 120)[names + refs]
    corr = sub.corr()
    res = {}
    for n in names:
        vals = {r: corr.loc[n, r] for r in refs if corr.loc[n, r] == corr.loc[n, r]}
        if vals:
            best = max(vals, key=lambda k: abs(vals[k]))
            res[n] = (float(vals[best]), best)
    return res


def _persist(lib: FactorLib, round_id: int, cand: dict, ev: dict,
             corr_info: tuple | None, corr_thr: float) -> str:
    """把单个候选因子的评估结果写入因子库，返回状态字符串。"""
    name = cand["name"]
    if ev.get("error"):
        lib.add_factor(name, cand["expr"], cand["logic"], "invalid",
                       round_id=round_id, fail_reason=ev["error"])
        return "invalid"

    if corr_info and abs(corr_info[0]) >= corr_thr:
        lib.mark_duplicate(name, cand["expr"], cand["logic"], -1, round_id)
        return "duplicate"

    fid = lib.add_factor(name, cand["expr"], cand["logic"], "valid", round_id=round_id)
    if fid is None:
        return "duplicate"
    for seg in ("full", "is", "oos"):
        if seg in ev:
            lib.add_metrics(fid, seg, False, ev[seg])
            if seg + "_neu" in ev:
                lib.add_metrics(fid, seg, True, ev[seg + "_neu"])
    return "valid"


def run_batch(client: LLMClient, lib: FactorLib, round_id: int, n_new: int,
              refs: dict[str, str], split: str, corr_thr: float) -> dict:
    """一批闭环：生成 n_new 个 → 精确去重 → 一次批量评估 → 相关去重 → 入库。

    参数 refs 为 {参照列名: 参照表达式}。
    返回本轮计数 {generated, duplicate, invalid, valid, details}。
    """
    prompt = build_user_prompt(lib.recent_failures(), lib.existing_logics())
    existing = lib.existing_exprs()

    gen, new = [], []
    for i in range(n_new):
        try:
            f = generate_factor(client, prompt)
        except Exception as e:  # noqa: BLE001
            lib.add_factor(f"gen_fail_{round_id}_{i}", expr=f"ERR:{round_id}:{i}",
                           logic="", status="invalid", round_id=round_id,
                           fail_reason=str(e)[:160])
            print(f"  [生成失败] {e}")
            continue
        gen.append(f)
        if normalize_expr(f["expr"]) in existing:
            lib.mark_duplicate(f["name"], f["expr"], f["logic"], -1, round_id)
            print(f"  [重复表达式] {f['name']}")
            continue
        existing[normalize_expr(f["expr"])] = -1
        new.append(f)

    cnt = {"generated": len(gen), "duplicate": len(gen) - len(new),
           "invalid": 0, "valid": 0, "details": []}
    if not new:
        return cnt

    names = [f["name"] for f in new]
    exprs = [f["expr"] for f in new]
    ref_cols, ref_exprs = list(refs), list(refs.values())
    try:
        df = load_factor_data(exprs + ref_exprs, names + ref_cols)
        df = winsorize_zscore(df, names + ref_cols)
        try:
            df = add_industry_columns(df)
            for n in names:
                df[n + "_neu"] = df[n]
            df = industry_neutral(df, [n + "_neu" for n in names])
        except FileNotFoundError as e:
            print(f"  [跳过行业中性] {e}")
    except Exception as e:  # noqa: BLE001
        # 整批加载失败：常见于某个表达式非法，逐个隔离定位并记为非法
        print(f"  [批量加载失败，逐个定位] {str(e)[:120]}")
        for f in new:
            st = _persist_one(lib, round_id, f, split)
            cnt[st] += 1
            cnt["details"].append(st)
        return cnt

    ev = evaluate_segments(df, names, split)
    corr = max_corr_with_refs(df, names, ref_cols) if ref_cols else {}
    for f in new:
        st = _persist(lib, round_id, f, ev.get(f["name"], {"error": "no metric"}),
                      corr.get(f["name"]), corr_thr)
        cnt[st] += 1
        cnt["details"].append(st)
        m = ev.get(f["name"], {}).get("oos_neu") or ev.get(f["name"], {}).get("full") or {}
        c = corr.get(f["name"])
        print(f"  {f['name']:<26s} {st:<9s} OOS中性RankICIR="
              f"{str(m.get('RankICIR'))[:7]:>7s}"
              + (f" maxCorr={c[0]:+.2f}" if c else ""))
    return cnt


def _persist_one(lib: FactorLib, round_id: int, f: dict, split: str) -> str:
    """单个因子独立加载-评估-入库（批量加载失败时的隔离路径）。"""
    try:
        d1 = load_factor_data([f["expr"]], [f["name"]])
        d1 = winsorize_zscore(d1, [f["name"]])
        ev = evaluate_segments(d1, [f["name"]], split)
        return _persist(lib, round_id, f, ev[f["name"]], None, 1.1)
    except Exception as e:  # noqa: BLE001
        lib.add_factor(f["name"], f["expr"], f["logic"], "invalid",
                       round_id=round_id, fail_reason=str(e)[:160])
        return "invalid"


def build_refs(lib: FactorLib, n: int = 10) -> dict[str, str]:
    """参照因子（库内高分）：返回 {列名 ref_<id>: 表达式}，用于同质化判定。"""
    return {f"ref_{r['id']}": r["expr"] for r in lib.top_valid(n)}


def loop(client: LLMClient | None, batches: int, per_batch: int,
         split: str, corr_thr: float, log_path: Path) -> None:
    """闭环迭代主循环，逐批挖掘并落库，日志写项目内 data/bt_export/。"""
    lib = FactorLib()
    client = client or LLMClient()
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(f"\n===== loop 启动 {datetime.now().isoformat(timespec='seconds')} "
                  f"batches={batches} per_batch={per_batch} =====\n")
        for b in range(batches):
            refs = build_refs(lib)
            rid = lib.start_round(note=f"batch{b}")
            print(f"\n===== 第 {b+1}/{batches} 批（参照 {len(refs)} 个高分因子）=====")
            try:
                cnt = run_batch(client, lib, rid, per_batch, refs, split, corr_thr)
            except Exception as e:  # noqa: BLE001
                print(f"  [本批异常，跳过] {str(e)[:200]}")
                log.write(f"batch{b} ERROR {e}\n")
                log.flush()
                continue
            lib.finish_round(rid, cnt["generated"], cnt["valid"],
                             cnt["invalid"], cnt["duplicate"])
            line = (f"batch{b}: 生成{cnt['generated']} 有效{cnt['valid']} "
                    f"非法{cnt['invalid']} 同质{cnt['duplicate']}")
            print(line)
            log.write(line + "\n")
            log.flush()
    s = lib.stats()
    print("\n===== 库统计 =====")
    for k, v in s.items():
        print(f"  {k}: {v if not isinstance(v, float) else round(v, 4)}")
    lib.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="因子挖掘闭环")
    ap.add_argument("cmd", choices=["mine", "loop", "smoke", "seed", "stats"])
    ap.add_argument("-n", "--num", type=int, default=3, help="mine: 单轮因子数")
    ap.add_argument("-b", "--batches", type=int, default=10, help="loop: 批次数量")
    ap.add_argument("--per-batch", type=int, default=6, help="loop: 每批生成因子数")
    ap.add_argument("--split", default="2025-08-01", help="IS/OOS 切分日")
    ap.add_argument("--corr", type=float, default=0.90, help="同质化判定阈值")
    args = ap.parse_args()

    from research.config import bt_export_dir

    if args.cmd == "stats":
        lib = FactorLib()
        for k, v in lib.stats().items():
            print(f"  {k}: {v if not isinstance(v, float) else round(v, 4)}")
        print("\n  TOP 有效因子（OOS 中性 RankICIR）:")
        for r in lib.top_valid(15):
            print(f"    {r['name']:<26s} {r['oos_neu_ricir']:+.3f}  {r['expr'][:60]}")
        lib.close()
        return

    if args.cmd == "seed":
        lib = FactorLib()
        rid = lib.start_round(note="seed")
        for f in SEED_FACTORS:
            fid = lib.add_factor(f["name"], f["expr"], f["logic"], "valid",
                                 round_id=rid, src="seed")
            print(f"  {f['name']}: {'新增' if fid else '已存在'}")
        df = load_factor_data([f["expr"] for f in SEED_FACTORS],
                              [f["name"] for f in SEED_FACTORS])
        df = winsorize_zscore(df, [f["name"] for f in SEED_FACTORS])
        try:
            df = add_industry_columns(df)
            for f in SEED_FACTORS:
                df[f["name"] + "_neu"] = df[f["name"]]
            df = industry_neutral(df, [f["name"] + "_neu" for f in SEED_FACTORS])
        except FileNotFoundError as e:
            print(f"  [跳过行业中性] {e}")
        ev = evaluate_segments(df, [f["name"] for f in SEED_FACTORS], args.split)
        lib.conn.execute("DELETE FROM metrics WHERE factor_id IN"
                         " (SELECT id FROM factors WHERE src='seed')")
        for f in SEED_FACTORS:
            row = lib.conn.execute("SELECT id FROM factors WHERE expr_norm=?",
                                   (normalize_expr(f["expr"]),)).fetchone()
            if not row:
                continue
            for seg in ("full", "is", "oos"):
                if seg in ev[f["name"]]:
                    lib.add_metrics(row["id"], seg, False, ev[f["name"]][seg])
                    if seg + "_neu" in ev[f["name"]]:
                        lib.add_metrics(row["id"], seg, True, ev[f["name"]][seg + "_neu"])
            m = ev[f["name"]].get("oos_neu") or {}
            print(f"  {f['name']:<20s} OOS中性RankICIR={str(m.get('RankICIR'))[:7]}")
        lib.close()
        return

    if args.cmd == "smoke":
        exprs = ["Mean($amount,5)/Mean($amount,50)", "Std($close,20)/Mean($close,20)"]
        names = ["turnover_ratio", "vol_20"]
        df = load_factor_data(exprs, names)
        df = winsorize_zscore(df, names)
        for n in names:
            m = evaluate_factor(df, n)
            print(f"  {n}: RankICIR={m['RankICIR']:.4f}")
        print("smoke 通过。")
        return

    client = LLMClient()
    if args.cmd == "loop":
        loop(client, args.batches, args.per_batch, args.split, args.corr,
             bt_export_dir() / "loop.log")
        return

    # mine：单轮（保留原用途，结果同时入库）
    lib = FactorLib()
    rid = lib.start_round(note="mine")
    prompt = build_user_prompt(lib.recent_failures(), lib.existing_logics())
    factors = []
    for i in range(args.num):
        print(f"\n===== 生成第 {i+1}/{args.num} 个 =====")
        try:
            r = generate_factor(client, prompt)
            print(f"  {r['name']}: {r['expr']}")
            factors.append(r)
        except Exception as e:  # noqa: BLE001
            print(f"  [生成失败] {e}")
    names = [f["name"] for f in factors]
    df = load_factor_data([f["expr"] for f in factors], names)
    df = winsorize_zscore(df, names)
    try:
        df = add_industry_columns(df)
        for n in names:
            df[n + "_neu"] = df[n]
        df = industry_neutral(df, [n + "_neu" for n in names])
    except FileNotFoundError as e:
        print(f"  [跳过行业中性] {e}")
    ev = evaluate_segments(df, names, args.split)
    for f in factors:
        st = _persist(lib, rid, f, ev.get(f["name"], {"error": "no metric"}), None, 1.1)
        m = ev.get(f["name"], {}).get("oos_neu") or {}
        print(f"  {f['name']:<24s} {st:<9s} OOS中性RankICIR={str(m.get('RankICIR'))[:7]}")
    lib.finish_round(rid, len(factors),
                     sum(1 for f in factors if ev.get(f['name'], {}).get('full')), 0, 0)
    lib.close()


if __name__ == "__main__":
    main()
