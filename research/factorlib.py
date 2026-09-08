# -*- coding: utf-8 -*-
"""私有因子库（L4 工具契约层）：因子档案 + 状态机 + 去重索引

FACTORS.md 是人读台账，本模块是机器读账本（data/derived/factorlib.json）。
L4 挖掘闭环的"记忆"：假设器每次开工前先读它（去重、看失败教训），
裁判评完写回它，淘汰哨兵定期改它状态。

状态机：
    candidate（候选）→ product（产品/在役）→ retired（退役/失效）
    candidate → rejected（拒收：没过裁判及格线，留失败原因）

记录字段（一条因子一档）：
    name / expr / status / created / updated / hypothesis（假设与动机）
    eval（最近一次 eval JSON 摘要）/ backtest（组合成绩摘要，可空）
    history（状态流转与备注流水账，失败教训就在这里——回喂假设器用）

用法：
    conda run -n jaycode python -m research.factorlib list
    conda run -n jaycode python -m research.factorlib show <name>
    conda run -n jaycode python -m research.factorlib add --name a_x \
        --expr "..." --hypothesis "..." [--status candidate]
    conda run -n jaycode python -m research.factorlib set-status <name> \
        <status> --note "判决理由"
    conda run -n jaycode python -m research.factorlib record-eval <name> \
        --json '<eval --json 的原始输出>'
"""

from __future__ import annotations

import argparse
import datetime
import json

from research.config import derived_dir

VALID = ("candidate", "product", "retired", "rejected")
# 状态机允许的流转（product 只能从 candidate 升；retired/rejected 可复活为候选）
ALLOW = {
    "candidate": {"product", "retired", "rejected"},
    "product": {"retired"},
    "retired": {"candidate"},
    "rejected": {"candidate"},
}


def lib_path():
    return derived_dir() / "factorlib.json"


def load() -> dict:
    p = lib_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"version": 1, "factors": {}}


def save(lib: dict) -> None:
    lib_path().write_text(json.dumps(lib, ensure_ascii=False, indent=1),
                          encoding="utf-8")


def _now() -> str:
    return datetime.date.today().isoformat()


def _log(rec: dict, msg: str) -> None:
    rec["history"].append(f"{_now()} {msg}")


def cmd_list(lib: dict, status: str = "") -> None:
    rows = [(n, r["status"], r.get("expr", "")[:44],
             (r.get("eval") or {}).get("icir_neu_full"))
            for n, r in lib["factors"].items()
            if not status or r["status"] == status]
    print(json.dumps({"count": len(rows),
                      "factors": [{"name": n, "status": s, "expr": e,
                                   "icir_neu_full": ic} for n, s, e, ic in rows]},
                     ensure_ascii=False))


def cmd_show(lib: dict, name: str) -> None:
    rec = lib["factors"].get(name)
    if rec is None:
        print(json.dumps({"ok": False, "error": f"无此因子 {name}"},
                         ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps({"ok": True, "name": name, **rec}, ensure_ascii=False))


def cmd_add(lib: dict, name: str, expr: str, hypothesis: str,
            status: str) -> None:
    if name in lib["factors"]:
        print(json.dumps({"ok": False, "error": f"已存在 {name}（去重纪律：换思路）"},
                         ensure_ascii=False))
        raise SystemExit(1)
    if status not in VALID:
        raise SystemExit(f"status 必须是 {VALID}")
    lib["factors"][name] = {
        "expr": expr, "status": status, "created": _now(), "updated": _now(),
        "hypothesis": hypothesis, "eval": None, "backtest": None,
        "history": [f"{_now()} 建档（{status}）"],
    }
    save(lib)
    print(json.dumps({"ok": True, "name": name, "status": status},
                     ensure_ascii=False))


def cmd_set_status(lib: dict, name: str, status: str, note: str) -> None:
    rec = lib["factors"].get(name)
    if rec is None:
        raise SystemExit(f"无此因子 {name}")
    if status not in ALLOW.get(rec["status"], set()):
        raise SystemExit(f"非法流转 {rec['status']} → {status}"
                         f"（允许 {sorted(ALLOW[rec['status']])}）")
    rec["status"] = status
    rec["updated"] = _now()
    _log(rec, f"状态→{status}：{note}")
    save(lib)
    print(json.dumps({"ok": True, "name": name, "status": status},
                     ensure_ascii=False))


def cmd_record_eval(lib: dict, name: str, eval_json: str) -> None:
    """把 eval --json 的原始输出摘要进档案（裁判结果自动回写）。"""
    rec = lib["factors"].get(name)
    if rec is None:
        raise SystemExit(f"无此因子 {name}（先 add）")
    try:
        ev = json.loads(eval_json)
    except json.JSONDecodeError as e:
        raise SystemExit(f"不是合法 JSON: {e}")
    if not ev.get("ok"):
        raise SystemExit("eval 输出 ok=false，不入库")
    seg = ev["segments"]
    key = lambda k, f: (seg.get(k) or {}).get(f)
    rec["eval"] = {
        "date": _now(), "label": ev["label"],
        "ric_raw_full": key("full/raw", "RankIC"),
        "ric_neu_full": key("full/neu", "RankIC"),
        "icir_neu_full": key("full/neu", "ICIR"),
        "ric_neu_IS": key("IS/neu", "RankIC"),
        "ric_neu_OOS": key("OOS/neu", "RankIC"),
    }
    _log(rec, f"eval 记录：neu_full ICIR={rec['eval']['icir_neu_full']:+.3f}")
    save(lib)
    print(json.dumps({"ok": True, "name": name, **rec["eval"]},
                     ensure_ascii=False))


def cmd_exprs(lib: dict) -> None:
    """假设器去重用：所有在册表达式的紧凑清单。"""
    print(json.dumps(
        {n: {"expr": r["expr"], "status": r["status"]}
         for n, r in lib["factors"].items()}, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(description="私有因子库（机器账本）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sp = sub.add_parser("show"); sp.add_argument("name")
    ad = sub.add_parser("add")
    ad.add_argument("--name", required=True); ad.add_argument("--expr", required=True)
    ad.add_argument("--hypothesis", required=True)
    ad.add_argument("--status", default="candidate")
    st = sub.add_parser("set-status")
    st.add_argument("name"); st.add_argument("status")
    st.add_argument("--note", required=True)
    re_ = sub.add_parser("record-eval")
    re_.add_argument("name"); re_.add_argument("--json", required=True)
    sub.add_parser("exprs")
    a = ap.parse_args()

    lib = load()
    if a.cmd == "list":
        cmd_list(lib)
    elif a.cmd == "show":
        cmd_show(lib, a.name)
    elif a.cmd == "add":
        cmd_add(lib, a.name, a.expr, a.hypothesis, a.status)
    elif a.cmd == "set-status":
        cmd_set_status(lib, a.name, a.status, a.note)
    elif a.cmd == "record-eval":
        cmd_record_eval(lib, a.name, getattr(a, "json"))
    elif a.cmd == "exprs":
        cmd_exprs(lib)


if __name__ == "__main__":
    main()
