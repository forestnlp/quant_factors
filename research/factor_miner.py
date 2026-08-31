# -*- coding: utf-8 -*-
"""本地 DeepSeek 驱动——单轮因子挖掘最小闭环（research 中间区）

对应项目目标 Phase1「原型打通」：跑通「Prompt → DeepSeek 生成因子代码 →
Qlib IC/IR 评估 → 输出结果」的最小链路，验证可行性，暂不做循环迭代。

流程（本轮）：
    1. 构造结构化 Prompt（约束输出 JSON，注入字段规范 + 示例 + 历史避坑）
    2. 调本地 DeepSeek（llm_client），得到候选因子 {name, expr, logic}
    3. 用 research.factor_eval 加载数据并评估 IC / RankIC / ICIR
    4. 表达式非法或评估失败时，把错误喂回模型重试一次

用法：
    conda run -n jaycode python research/factor_miner.py mine        # 真实调用 DeepSeek
    conda run -n jaycode python research/factor_miner.py smoke       # 不调 LLM，仅验评估链
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from research.factor_eval import evaluate_factor, load_factor_data, winsorize_zscore  # noqa: E402
from research.llm_client import LLMClient  # noqa: E402

# ---------- Qlib 可用字段与表达式规范（注入 prompt）----------
AVAILABLE_FIELDS = "$open $high $low $close $vwap $volume $amount"

EXPR_RULES = (
    "只允许使用 qlib Alpha158 风格表达式："
    "Ref($x,k) 引用第 k 日前；Mean/Std/Sum/Max/Min(x,n) 滚动窗口；"
    "Corr(x,y,n)/Cov 相关系数；Log/Exp/Abs；EMA($x,n)；Rank(x,cond) 截面排名。"
    "禁止 Ref($x,-k) 取未来数据（未来函数）、禁止引入未知字段、禁止除数为零。"
)

FACTOR_EXAMPLES = [
    '{"name": "mom_accel", "expr": "($close / Ref($close,20)-1) - ($close/Ref($close,40)-1)", "logic": "动量加速度"}',
    '{"name": "turnover_ratio", "expr": "Mean($amount,5)/Mean($amount,50)", "logic": "量能比"}',
]

SYSTEM_PROMPT = f"""你是一名资深量化因子研究员，为 A 股全市场横截面选股设计**日线量价因子**。
本地 Qlib 数据集仅含以下字段：{AVAILABLE_FIELDS}。

{EXPR_RULES}

你必须严格输出一个 JSON 对象，不要任何解释文字、不要 markdown 代码块。格式：
{{"name":"因子名(英文字母下划线)","expr":"Qlib表达式","logic":"一句话逻辑假设"}}

参考示例（仅示意格式）：
{FACTOR_EXAMPLES[0]}
{FACTOR_EXAMPLES[1]}

要求：因子需有明确的金融逻辑假设；与已知简单动量/换手因子差异化；表达式可被 Qlib 解析。
"""


def build_user_prompt() -> str:
    """构造本轮挖掘任务指令（可扩展注入历史成败案例上下文）。"""
    return (
        "请基于 A 股近三年震荡市环境，提出 3 个全新的、有独立逻辑的量价日线因子。"
        "注意：当前市场有效信号偏『负向』（放量/高波动后收益偏低），"
        "优先探索成交量结构、量价背离、波动率聚簇、开盘/收盘相对位置等维度。"
        "每个因子都要给出唯一名字、合法 Qlib 表达式、以及一句话逻辑假设。"
    )


def parse_factor_json(text: str) -> dict:
    """从模型输出中抽取并解析单个因子 JSON。"""
    # 去掉可能的 markdown 围栏
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
    """调用一次 DeepSeek，仅生成候选因子定义 {name, expr, logic}，不回测。

    失败时带错误喂回模型重试一次。
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    for attempt in (1, 2):
        text = client.chat(messages, temperature=0.4, max_tokens=4096)
        try:
            return parse_factor_json(text)
        except Exception as e:  # noqa: BLE001
            err = str(e)[:300]
            print(f"[第{attempt}次失败] {err}")
            if attempt == 1:
                retry_msg = ("你的输出解析/回测失败，错误：" + err +
                             "\n请重新严格输出单个 JSON 对象。")
                messages.append({"role": "user", "content": retry_msg})
    raise RuntimeError("重试后仍失败")


def _eval_batch(factors: list[dict]) -> list[dict]:
    """一次性批量加载并评估多个因子（避免每因子重复 IO）。

    返回：每个因子附带 IC_mean / ICIR / RankIC_mean / RankICIR / n_days。
    """
    valid = [f for f in factors if f.get("expr")]
    if not valid:
        return []
    exprs = [f["expr"] for f in valid]
    names = [f["name"] for f in valid]
    df = load_factor_data(exprs, names)          # 一次加载全库
    df = winsorize_zscore(df, names)             # 截面缩尾标准化
    for f, name in zip(valid, names):
        try:
            metric = evaluate_factor(df, name)
            f.update({k: (float(metric[k]) if metric[k] == metric[k] else None)
                      for k in ["IC_mean", "ICIR", "RankIC_mean", "RankICIR", "IC_positive_ratio"]})
            f["n_days"] = int(metric["n_days"]) if metric["n_days"] == metric["n_days"] else None
        except Exception as e:  # noqa: BLE001
            print(f"  [评估失败 {name}] {e}")
            f["eval_error"] = str(e)[:100]
    return valid


def mine(client: LLMClient | None = None, n_factors: int = 3) -> list[dict]:
    """执行单轮挖掘闭环：先生成 n 个因子定义，再一次性批量回测评估。"""
    client = client or LLMClient()
    user_prompt = build_user_prompt()

    factors = []
    for i in range(n_factors):
        print(f"\n========== 生成第 {i+1}/{n_factors} 个因子 ==========")
        try:
            r = generate_factor(client, user_prompt)
            print(f"  {r['name']}: {r['expr']}")
            print(f"    逻辑: {r.get('logic','')}")
            factors.append(r)
        except Exception as e:  # noqa: BLE001
            print(f"  [生成失败] {e}")

    print(f"\n=== 批量回测 {len(factors)} 个因子 ===")
    results = _eval_batch(factors)
    for r in results:
        if "eval_error" in r:
            print(f"  {r['name']}: 评估失败 {r['eval_error']}")
        else:
            print(f"  {r['name']:<24s} RankIC={str(r.get('RankIC_mean'))[:7]:>7s}"
                  f"  RankICIR={str(r.get('RankICIR'))[:7]:>7s}"
                  f"  ICIR={str(r.get('ICIR'))[:7]:>7s}  n_days={r.get('n_days')}")
    return results


def smoke() -> dict:
    """不调 LLM，用固定表达式验证评估链可用（Phase1 自检）。"""
    from research.factor_eval import HORIZON
    exprs = ["Mean($amount,5)/Mean($amount,50)", "Std($close,20)/Mean($close,20)"]
    names = ["turnover_ratio", "vol_20"]
    df = load_factor_data(exprs, names, horizon=HORIZON)
    df = winsorize_zscore(df, names)
    return {n: evaluate_factor(df, n).to_dict() for n in names}


def main() -> None:
    ap = argparse.ArgumentParser(description="单轮因子挖掘最小闭环")
    ap.add_argument("cmd", choices=["mine", "smoke"], help="mine=真实调LLM; smoke=验评估链")
    ap.add_argument("-n", "--num", type=int, default=3, help="挖掘因子数量")
    ap.add_argument("-o", "--out", default=None,
                    help="结果输出 CSV（缺省 data/bt_export/factor_mine_result.csv）")
    args = ap.parse_args()

    if args.cmd == "smoke":
        print("=== smoke：验证 Qlib 评估链 ===")
        for name, metric in smoke().items():
            print(f"  {name}: RankICIR={metric['RankICIR']:.4f} ICIR={metric['ICIR']:.4f}")
        print("\nsmoke 通过。")
        return

    print("=== mine：本地 DeepSeek 单轮因子挖掘 ===")
    client = LLMClient()
    results = mine(client, n_factors=args.num)

    # 落盘结果，避免管道缓冲导致实时不可见
    import pandas as pd
    from research.config import PROJECT_ROOT
    out_path = Path(args.out) if args.out else \
        PROJECT_ROOT / "data" / "bt_export" / "factor_mine_result.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(results)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n==== 本轮挖掘汇总（{len(results)} 个有效） ====")
    for r in results:
        if "eval_error" in r:
            print(f"  {r['name']:>24s} | 评估失败: {r['eval_error']}")
        else:
            print(f"  {r['name']:>24s} | RankICIR={str(r.get('RankICIR'))[:7]:>7s}"
                  f" | ICIR={str(r.get('ICIR'))[:7]:>7s} | {r.get('expr','')}")
    print(f"\n已保存: {out_path}")


if __name__ == "__main__":
    main()
