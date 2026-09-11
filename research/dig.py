# -*- coding: utf-8 -*-
"""L4 自动挖掘回路（假设器上岗）：propose→compile→judge→memorize 全自动闭环

流程代码写死，只在"提假设"一个节点调本地 Qwen（OpenAI 兼容端点，.env 配置）。
七形态对策逐条落码（PROJECT.md 七形态表）：
  #1 故障伪装业务结果 → InfraError（网络/认证/超时/协议畸变）一律中止整轮运行，
     绝不记为因子判决；业务拒收（编译错/IC 不过）才回喂假设器。
  #2 同质化坍塌     → 表达式规范化去重 + 与在库 active 因子日截面秩相关 >0.9 拒收。
  #3 指标爬升真实力降 → 回喂给 LLM 的只有 IS 数字（全区间/OOS 不进对话）。
  #4 窗口过拟合     → 一次假设=一次判决，不许改参重试；机制连续 2 次失败拉黑。
  #6 成本失控       → 硬预算：--rounds 上限 + 连续 --patience 轮零产出自动停机。
  #7 静默卡死       → 每轮追加 data/derived/dig_log.jsonl（心跳线），stats 可查。

及格线（预注册 v2，2026-09-10 经用户批准收紧；候选通胀事故后改标准）：
  IC 初裁：IS/neu |ICIR| > 0.40（旧 0.25 系单发人工审口径，机器 7×24 下失效：
           09-09 一夜 80 假设 20 过线=按运气也该中，IS 门槛已筛不掉噪声）
  组合终裁：IS 费后年化 > 0 且 IS Sharpe ≥ --baseline（默认 0.55 = 现役产品
           a_rev_x_lowvol IS 0.58 同档；旧 0.46 门槛放进一整族换皮枪）
  方向：回测方向与 IS/neu RankIC 符号强制联动（IC>0 → reverse 做多高值端，规则6例外）
  回路产出的最高状态 = candidate（升 product 必须人工发起 WFO 预注册，机器不自封产品）

用法：
    conda run -n jaycode python -m research.dig run --rounds 5
    conda run -n jaycode python -m research.dig stats        # 心跳与战果
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from research import alpha, backtest as bt, eval as ev, factorlib
from research.config import derived_dir, llm_conf

PROPOSE_MD = Path(alpha.__file__).with_name("PROPOSE.md")
ICIR_GATE = 0.40          # IC 初裁及格线（IS/neu，2026-09-10 收紧：旧 0.25）
CORR_CAP = 0.90           # 与在库 active 因子秩相关上限（#2 去重）
MAX_FAIL_MECH = 2         # 同机制连续失败次数 → 拉黑
GRAVE_MIN = 3             # 跨批机制败部门槛：v2 新门以来同机制被拒次数 ≥ 此值入黑名单


class InfraError(Exception):
    """基础设施故障（#1）：中止运行，绝不进因子判决。"""


# ---------------- LLM 假设器 ----------------

V2_TS = "2026-09-10T09"   # 新门 v2 上线时刻（机制败部账本只记 v2 后的判决，旧门数据口径不可比）


def mech_graveyard() -> list[str]:
    """跨批机制墓地：从心跳线统计 v2 新门以来同机制被拒次数 ≥GRAVE_MIN 的机制。

    （09-11 补：原机制黑名单只活在单批内存里，换批即失忆——LLM 会反复重挖
    同一具尸体。心跳线 dig_log.jsonl 本就每轮带 mechanism+verdict，直接汇总。）"""
    p = derived_dir() / "dig_log.jsonl"
    if not p.exists():
        return []
    cnt: dict[str, int] = {}
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if (r.get("verdict") == "REJECT" and r.get("ts", "") >= V2_TS
                and r.get("mechanism")):
            m = str(r["mechanism"])[:24]
            cnt[m] = cnt.get(m, 0) + 1
    return sorted(m for m, c in cnt.items() if c >= GRAVE_MIN)


def _llm(messages: list[dict]) -> str:
    """调 OpenAI 兼容端点（JSON mode）。一切传输/协议异常 → InfraError。"""
    base, key, model = llm_conf()
    try:
        r = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": messages,
                  "response_format": {"type": "json_object"},
                  "max_tokens": 4000},
            timeout=(10, 600))
    except requests.RequestException as e:
        raise InfraError(f"LLM 通道故障: {e}") from None
    if r.status_code != 200:
        raise InfraError(f"LLM HTTP {r.status_code}: {r.text[:200]}")
    try:
        msg = r.json()["choices"][0]["message"]
    except (KeyError, IndexError, ValueError) as e:
        raise InfraError(f"LLM 响应协议畸变: {e}") from None
    # qwen3 reasoning 模型：JSON 可能落在 content 或 reasoning（思维链里）
    return (msg.get("content") or "") + "\n" + (msg.get("reasoning") or "")


def _extract_json(text: str) -> dict | None:
    """取**第一个**合法 JSON：content 拼在 reasoning 之前，正文答案先出现。
    （思维链里的草稿/模板 {"name","expr"} 不是合法 JSON，loads 自然跳过。）"""
    for m in re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text):
        try:
            d = json.loads(m)
        except ValueError:
            continue
        if isinstance(d, dict) and all(k in d for k in
                                       ("name", "expr", "hypothesis")) \
                and isinstance(d["name"], str):
            d.setdefault("mechanism", "未标注")
            return d
    return None


def propose(cols: list[str], exprs: dict, recap: list[dict],
            blacklist: list[str],
            graveyard: list[str] | None = None) -> dict | None:
    """一次假设（JSON mode）。内容畸变=业务级失败（返回 None），传输故障=InfraError。

    exprs 带状态（name→[status, expr]）：死路（rejected/retired）单独成段点名，
    让模型明知山有虎避开那山（09-11：190 条败部此前与活枪混排，等于没区分）。
    graveyard=跨批机制墓地（mech_graveyard 汇总），与本批黑名单合并去重。"""
    spec = open(PROPOSE_MD, encoding="utf-8").read()
    sys_p = (
        "你是量化因子假设器（L4 回路），严格遵守以下作业规范：\n\n" + spec +
        "\n\n可用列（宽表真实列，日期/代码/标签列已剔除）: " + ", ".join(cols) +
        "\n算子白名单: rank delay delta ts_mean ts_std ts_sum ts_min ts_max "
        "ts_corr log abs sign relu clip；四则+幂运算；时序窗口≤250。"
        "\n因子名必须以 a_ 开头的新名字（小写下划线，别用数字年份）。"
        "\n思维从简（3 句以内），把输出预算留给 JSON 本身，先写 JSON 再解释。"
        "\n只输出 JSON: {\"name\":..., \"expr\":..., \"hypothesis\":\"一句话经济逻辑\","
        " \"mechanism\":\"机制短标签\"}")
    # 原料多样性约束（首批教训 09-09：6/6 过线枪全含 mf_net_pct_main=同原料换配方）
    ing: dict[str, int] = {}
    for st_e in exprs.values():
        for c in cols:
            if c in st_e[1]:
                ing[c] = ing.get(c, 0) + 1
    hot = [f"{c}({n}次)" for c, n in sorted(ing.items(), key=lambda x: -x[1])[:6]
           if n >= 3]
    live = {n: e for n, (s, e) in exprs.items() if s in ("candidate", "product")}
    dead = sorted(n for n, (s, _) in exprs.items()
                  if s in ("rejected", "retired"))
    user_p = ("在册活枪表达式（严禁等价改写或换皮）:\n" +
              json.dumps(live, ensure_ascii=False) +
              f"\n\n已验证死路 {len(dead)} 条（这些因子全部被拒/退役，禁止同机制变体再试；"
              "完整表达式可按需自查，先列名）:\n" + ", ".join(dead) +
              "\n\n已过度使用的原料: " + (", ".join(hot) if hot else "（无）") +
              "——除非经济逻辑特别硬，否则必须改用未用过的原料组合新矿，别再围着它们换配方。" +
              "\n\n机制黑名单（连续失败，勿再碰）: " +
              (", ".join(sorted(set(blacklist) | set(graveyard or []))) or "（无）") +
              "\n\n最近判决复盘（只给 IS 数字）:\n" +
              json.dumps(recap[-8:], ensure_ascii=False))
    for _ in range(2):                      # 内容畸变重试一次
        content = _llm([{"role": "system", "content": sys_p},
                        {"role": "user", "content": user_p}])
        d = _extract_json(content)
        if d is not None:
            return d
    return None


# ---------------- 判决工具（全部复用既有资产） ----------------

def norm_expr(e: str) -> str:
    return re.sub(r"\s+", "", e)


def max_corr(f: pd.DataFrame, a: str, b: str) -> float:
    """两因子日截面秩相关的最大值（每 5 日采样，显式逐日循环）。

    教训（2026-09-08 首跑误杀全部候选）：groupby.corr() 每日出 4 行
    （a×a/a×b/b×a/b×b），旧写法 iloc 切片取到对角=恒 1.0；手写向量化
    Pearson 又被自检抓到不一致（结论14 同款教训）。
    终版姿势=显式逐日两侧同集合 rank + Series.corr()，简单压倒快。
    """
    if a == b:
        return 1.0
    sub = f[["dt", "code", a, b]].dropna()
    days = np.sort(sub["dt"].unique())[::5]
    best = 0.0
    for day in days:
        g = sub[sub["dt"] == day]
        if len(g) < 300:
            continue
        c = g[a].rank(pct=True).corr(g[b].rank(pct=True))
        if not np.isnan(c) and abs(c) > best:
            best = abs(c)
    return float(best)


def judge(f: pd.DataFrame, name: str, expr: str, baseline: float) -> dict:
    """编译→去重→IC 初裁→组合终裁。返回 {stage, pass, msg, is_view, corr}。
    is_view 只含 IS 数字（#3：全区间/OOS 不进 LLM 对话）。"""
    long = alpha.compile_expr(name, expr)       # CompileError=业务拒收
    p = alpha.alpha_dir() / f"{name}.parquet"
    long.to_parquet(p, index=False)

    f2 = ev._attach(f, name)
    st = ev.evaluate(f2, name)
    is_neu = st.get("IS/neu") or {}
    icir, ric = is_neu.get("ICIR"), is_neu.get("RankIC")
    if ric is None:
        return {"stage": "ic", "pass": False, "corr": None, "is_view": {},
                "msg": "IS 段无有效截面（数据覆盖不足）"}
    is_view = {"IS_RankIC": round(ric, 4), "IS_ICIR": round(icir, 4)}
    if abs(icir) <= ICIR_GATE:
        return {"stage": "ic", "pass": False, "corr": None, "is_view": is_view,
                "msg": f"IC 不及格：|IS/neu ICIR|={abs(icir):.3f} ≤ {ICIR_GATE}"}

    # 秩相关去重（#2）：与在库 active 因子逐个比
    lib = factorlib.load()
    worst, worst_n = 0.0, ""
    for n, rec in lib["factors"].items():
        if rec["status"] not in ("candidate", "product"):
            continue
        f3 = ev._attach(f2, n) if n not in f2.columns else f2
        c = max_corr(f3, name, n)
        if not np.isnan(c) and c > worst:
            worst, worst_n = c, n
    if worst > CORR_CAP:
        return {"stage": "dedup", "pass": False, "corr": round(worst, 3),
                "is_view": is_view,
                "msg": f"同质化：与 {worst_n} 秩相关 {worst:.2f} > {CORR_CAP}"}

    # 组合终裁：方向与 IC 符号强制联动（规则6例外条款）
    bt.RET_PATH = None
    bt.FEATURE_COLS = [name]
    res = bt.run(name, 100, 10, reverse=ric > 0,
                 band=(0.10, 0.50), quiet=True)
    is_view.update({"IS_ann": round(res["IS_ann"], 4),
                    "IS_Sharpe": round(res["IS_sharpe"], 3)})
    ok = res["IS_ann"] > 0 and res["IS_sharpe"] >= baseline
    msg = (f"组合终裁 IS 年化 {res['IS_ann']:+.1%} Sharpe {res['IS_sharpe']:.2f}"
           f"（基线 {baseline}）→ {'过线' if ok else '拒'}")
    return {"stage": "backtest", "pass": ok, "corr": round(worst, 3),
            "is_view": is_view, "msg": msg, "full": res}


def memorize(name: str, expr: str, hypothesis: str, j: dict) -> None:
    """过线入 candidate；IC 即拒也入库 rejected（失败教训回喂资产）。"""
    lib = factorlib.load()
    if name in lib["factors"]:
        return
    factorlib.cmd_add(lib, name, expr, hypothesis,
                      "candidate" if j["pass"] else "rejected")
    if j.get("is_view"):
        lib["factors"][name]["backtest"] = json.dumps(
            j["is_view"], ensure_ascii=False)
    factorlib._log(lib["factors"][name], f"L4 判决@{j['stage']}: {j['msg']}")
    factorlib.save(lib)


# ---------------- 回路 ----------------

def heartbeat(rec: dict) -> None:
    rec["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    with open(derived_dir() / "dig_log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def cmd_run(a: argparse.Namespace) -> None:
    base_cols = alpha.feature_columns()
    print(f"加载评估样本（一次性，全回路复用）...")
    f, _ = ev.load()

    recap: list[dict] = []
    mech_fails: dict[str, int] = {}
    blacklist: list[str] = []
    zero_streak, n_pass = 0, 0

    for rnd in range(1, a.rounds + 1):
        # 在册表达式去重索引每轮重读（本轮入库的也要防）；带状态供假设器区分活枪/死路
        lib = factorlib.load()
        exprs = {n: (r["status"], r["expr"]) for n, r in lib["factors"].items()}
        prop = propose(base_cols, exprs, recap, blacklist, mech_graveyard())
        if prop is None:
            recap.append({"round": rnd, "verdict": "畸变",
                          "msg": "输出非合法 JSON/缺字段（已重试一次）"})
            heartbeat({"round": rnd, "stage": "propose", "verdict": "malformed"})
            print(f"[{rnd}] 假设输出畸变，记业务失败（不入库）")
            zero_streak += 1
        else:
            name, expr = prop["name"], prop["expr"]
            mech = prop["mechanism"]
            dup = norm_expr(expr) in {norm_expr(e[1]) for e in exprs.values()}
            if dup or name in exprs:
                recap.append({"round": rnd, "name": name, "verdict": "重复",
                              "msg": "表达式或名字与在册重复"})
                heartbeat({"round": rnd, "name": name, "stage": "dedup",
                           "verdict": "duplicate"})
                print(f"[{rnd}] {name} 重复发明，拒")
                zero_streak += 1
            else:
                try:
                    j = judge(f, name, expr, a.baseline)
                except alpha.CompileError as e:
                    j = {"stage": "compile", "pass": False, "is_view": {},
                         "msg": f"编译拒收: {e}"}
                recap.append({"round": rnd, "name": name,
                              "verdict": "PASS" if j["pass"] else "REJECT",
                              "stage": j["stage"], "msg": j["msg"],
                              "is": j.get("is_view")})
                memorize(name, expr, prop["hypothesis"], j)
                heartbeat({"round": rnd, "name": name, "expr": expr,
                           "mechanism": mech, "stage": j["stage"],
                           "verdict": "PASS" if j["pass"] else "REJECT",
                           "msg": j["msg"], "is": j.get("is_view")})
                print(f"[{rnd}] {name} @{j['stage']} → "
                      f"{'PASS' if j['pass'] else '拒'}：{j['msg']}")
                if j["pass"]:
                    n_pass += 1
                    zero_streak = 0
                    mech_fails[mech] = 0
                else:
                    zero_streak += 1
                    mech_fails[mech] = mech_fails.get(mech, 0) + 1
                    if mech_fails[mech] >= MAX_FAIL_MECH and mech not in blacklist:
                        blacklist.append(mech)
                        print(f"  机制『{mech}』连续失败，拉黑")
        if zero_streak >= a.patience:
            print(f"连续 {zero_streak} 轮零产出 → 预算停机（#6）")
            break
    print(f"回路收工：{len(recap)} 轮，过线 {n_pass} 个（状态=candidate，"
          f"升 product 须人工 WFO 预注册）")


def cmd_stats(_: argparse.Namespace) -> None:
    """一屏仪表盘：库存量（账本）+ 生产速率（心跳线）+ 一句话健康判决。"""
    p = derived_dir() / "dig_log.jsonl"
    lib = factorlib.load()
    cnt: dict[str, int] = {}
    for r in lib["factors"].values():
        cnt[r["status"]] = cnt.get(r["status"], 0) + 1
    rows = ([json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
            if p.exists() else [])
    now = datetime.datetime.now()
    day_ago = (now - datetime.timedelta(hours=24)).isoformat(timespec="seconds")
    d24 = [r for r in rows if r.get("ts", "") >= day_ago]
    n24 = sum(1 for r in d24 if r.get("verdict") == "PASS")
    last_ts = rows[-1].get("ts", "") if rows else ""
    try:
        age_h = (now - datetime.datetime.fromisoformat(last_ts)).total_seconds() / 3600
    except ValueError:
        age_h = float("inf")
    verdict = ("健康" if age_h < 1.5 else "心跳停更（查 dig_health.log / 监工日志）")
    print(f"库存: candidate {cnt.get('candidate', 0)} | product {cnt.get('product', 0)}"
          f" | rejected {cnt.get('rejected', 0)} | retired {cnt.get('retired', 0)}")
    print(f"近 24h: 假设 {len(d24)} → 过线 {n24}（≈{n24 / 24:.1f} 支/小时）")
    print(f"最后心跳: {last_ts or '（无）'}（{age_h:.1f} 小时前）→ {verdict}")


def main() -> None:
    ap = argparse.ArgumentParser(description="L4 自动挖掘回路")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="跑挖掘回路")
    r.add_argument("--rounds", type=int, default=5)
    r.add_argument("--patience", type=int, default=3,
                   help="连续 N 轮零产出停机（#6）")
    r.add_argument("--baseline", type=float, default=0.55,
                   help="组合终裁 IS Sharpe 及格线（2026-09-10 收紧：旧 0.46）")
    r.set_defaults(func=cmd_run)
    sub.add_parser("stats", help="心跳线与战果").set_defaults(func=cmd_stats)
    a = ap.parse_args()
    try:
        a.func(a)
    except InfraError as e:
        # #1：基础设施故障 fail-fast 显式告警，绝不记为业务失败
        print(json.dumps({"ok": False, "infra": True, "error": str(e)},
                         ensure_ascii=False))
        raise SystemExit(3)


if __name__ == "__main__":
    main()
