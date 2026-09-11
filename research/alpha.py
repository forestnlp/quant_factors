# -*- coding: utf-8 -*-
"""表达式编译器（L4 工具契约层）：白名单 DSL → 宽表因子列

自动挖掘的"安全闸"：LLM 产出的因子表达式只允许引用宽表已有列 + 白名单算子，
经 AST 校验后编译执行——杜绝任意代码执行，且时序算子只用历史窗口（无未来函数）。

白名单：
    列名   = data/derived/features.parquet 的全部列
    算术   = + - * / **（除零→NaN）
    截面   = rank(x)                    当日截面百分位 [0,1]
    时序   = delay(x,n) delta(x,n) ts_mean(x,n) ts_std(x,n) ts_sum(x,n)
             ts_min(x,n) ts_max(x,n) ts_corr(x,y,n)      全部只用 [t-n, t]
    逐点   = log(x)（x<=0→NaN）abs(x) sign(x) relu(x)=max(x,0)
             clip(x,lo,hi) 双边饱和

产物落 data/derived/alpha/<name>.parquet（长表 date/code/value），
eval/sentinel 等工具按列名自动加载——与宽表列同一契约。

用法：
    conda run -n jaycode python -m research.alpha list-cols
    conda run -n jaycode python -m research.alpha compile \
        --name a_test --expr "rank(-r_20d) * rank(-v_std_20)"
"""

from __future__ import annotations

import argparse
import ast
import json

import numpy as np
import pandas as pd

from research.config import derived_dir

MAX_WINDOW = 250          # 时序窗口上限（交易日）
LABEL_PREFIX = "fwd_"     # 未来收益标签列前缀：严禁作因子输入（未来函数）


def alpha_dir():
    return derived_dir("alpha")


def wide_path():
    return derived_dir() / "features.parquet"


def wide_columns() -> list[str]:
    import pyarrow.parquet as pq
    return list(pq.ParquetFile(wide_path()).schema_arrow.names)


def feature_columns() -> list[str]:
    """允许进入表达式白名单的列：宽表列去掉 date/code 与一切 fwd_* 标签列。"""
    return [c for c in wide_columns()
            if c not in ("date", "code") and not c.startswith(LABEL_PREFIX)]


# ---------------- 算子（输入为宽表透视：index=date, columns=code） ----------------

def _n(v):
    if not isinstance(v, (int, float)) or float(v) != int(v) or int(v) < 1:
        raise ValueError(f"窗口参数必须是正整数，得到 {v!r}")
    return int(v)


def _win(n: int) -> int:
    n = _n(n)
    if n > MAX_WINDOW:
        raise ValueError(f"窗口 {n} 超上限 {MAX_WINDOW}")
    return n


def _rank(x: pd.DataFrame) -> pd.DataFrame:
    return x.rank(axis=1, pct=True)


_OPS = {
    "rank":    ([("x", "df")], _rank),
    "delay":   ([("x", "df"), ("n", "int")], lambda x, n: x.shift(_win(n))),
    "delta":   ([("x", "df"), ("n", "int")], lambda x, n: x - x.shift(_win(n))),
    "ts_mean": ([("x", "df"), ("n", "int")],
                lambda x, n: x.rolling(_win(n)).mean()),
    "ts_std":  ([("x", "df"), ("n", "int")],
                lambda x, n: x.rolling(_win(n)).std()),
    "ts_sum":  ([("x", "df"), ("n", "int")],
                lambda x, n: x.rolling(_win(n)).sum()),
    "ts_min":  ([("x", "df"), ("n", "int")],
                lambda x, n: x.rolling(_win(n)).min()),
    "ts_max":  ([("x", "df"), ("n", "int")],
                lambda x, n: x.rolling(_win(n)).max()),
    "ts_corr": ([("x", "df"), ("y", "df"), ("n", "int")],
                lambda x, y, n: x.rolling(_win(n)).corr(y)),
    "log":     ([("x", "df")], lambda x: np.log(x.where(x > 0))),
    "abs":     ([("x", "df")], lambda x: x.abs()),
    "sign":    ([("x", "df")], lambda x: x.sign()),
    # 逐点非线性（2026-09-11 增）：relu=只取正半边（单边信号）；clip=双边饱和
    "relu":    ([("x", "df")], lambda x: x.clip(lower=0.0)),
    "clip":    ([("x", "df"), ("lo", "num"), ("hi", "num")],
                lambda x, lo, hi: x.clip(float(lo), float(hi))),
}

_BIN_OK = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)


class CompileError(Exception):
    """表达式不合法（白名单外、类型/元数不符等）。"""


def _validate(node: ast.AST, cols: set[str], used: set[str]):
    """递归 AST 校验：只放行 白名单调用/算术/数字/列名，顺带收集用到的列。"""
    if isinstance(node, ast.Expression):
        _validate(node.body, cols, used)
    elif isinstance(node, ast.BinOp):
        if not isinstance(node.op, _BIN_OK):
            raise CompileError(f"禁用运算符: {type(node.op).__name__}")
        _validate(node.left, cols, used)
        _validate(node.right, cols, used)
    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.USub, ast.UAdd)):
            raise CompileError(f"禁用一元运算符: {type(node.op).__name__}")
        _validate(node.operand, cols, used)
    elif isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise CompileError(f"只允许数字常量，得到 {node.value!r}")
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _OPS:
            raise CompileError("只允许白名单算子调用: " + ", ".join(_OPS))
        name = node.func.id
        if node.keywords:
            raise CompileError(f"{name}() 不支持关键字参数")
        specs = _OPS[name][0]
        if len(node.args) != len(specs):
            raise CompileError(
                f"{name}() 需要 {len(specs)} 个参数，得到 {len(node.args)}")
        for arg, (_, kind) in zip(node.args, specs):
            if kind in ("int", "num"):
                # 负数常量在 AST 里是 UnaryOp(USub, Constant)，须一并放行
                ok = (isinstance(arg, ast.Constant)
                      and isinstance(arg.value, (int, float)))
                neg = (isinstance(arg, ast.UnaryOp) and _is_neg_const(arg))
                if not (ok or neg):
                    raise CompileError(f"{name}() 的参数必须是数字常量")
            else:
                _validate(arg, cols, used)
    elif isinstance(node, ast.Name):
        if node.id not in cols:
            raise CompileError(f"未知列: {node.id}")
        used.add(node.id)
    else:
        raise CompileError(f"禁用语法节点: {type(node).__name__}")


def _is_neg_const(arg: ast.UnaryOp) -> bool:
    return (isinstance(arg.op, ast.USub)
            and isinstance(arg.operand, ast.Constant)
            and isinstance(arg.operand.value, (int, float)))


class _Ctx:
    """按需把宽表列透视成宽矩阵（同一进程内缓存）。"""

    def __init__(self, cols: set[str]):
        need = sorted(cols | {"date", "code"})
        df = pd.read_parquet(wide_path(), columns=need)
        df = df.drop_duplicates(subset=["date", "code"])
        self._mats = {}
        for c in cols:
            w = df.pivot(index="date", columns="code", values=c)
            w.columns.name = None
            self._mats[c] = w

    def mat(self, col: str) -> pd.DataFrame:
        return self._mats[col]


def _eval(node: ast.AST, ctx: _Ctx) -> pd.DataFrame:
    if isinstance(node, ast.Expression):
        return _eval(node.body, ctx)
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return ctx.mat(node.id)
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, ctx)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        a, b = _eval(node.left, ctx), _eval(node.right, ctx)
        with np.errstate(all="ignore"):
            if isinstance(node.op, ast.Add):
                r = a + b
            elif isinstance(node.op, ast.Sub):
                r = a - b
            elif isinstance(node.op, ast.Mult):
                r = a * b
            elif isinstance(node.op, ast.Div):
                r = a / b
            else:
                r = a ** b
        if isinstance(r, pd.DataFrame):
            r = r.replace([np.inf, -np.inf], np.nan)
        return r
    if isinstance(node, ast.Call):
        name = node.func.id
        args = [_eval(a, ctx) for a in node.args]
        return _OPS[name][1](*args)
    raise CompileError(f"未处理的节点: {type(node).__name__}")


def compile_expr(name: str, expr: str) -> pd.DataFrame:
    """表达式 → 长表因子（date/code/value），只含非 NaN 行。"""
    if not name.isidentifier() or name in _OPS or name in wide_columns():
        raise CompileError(f"非法因子名 {name!r}：须为标识符且不撞算子/宽表列名")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise CompileError(f"语法错误: {e}") from None
    cols = set(feature_columns())
    used: set[str] = set()
    _validate(tree, cols, used)
    mat = _eval(tree, _Ctx(used))
    if not isinstance(mat, pd.DataFrame):
        raise CompileError("表达式必须是列的函数（结果是标量无意义）")
    mat.index.name = "date"
    mat.columns.name = "code"
    long = mat.stack().rename("value").dropna().reset_index()
    long["value"] = long["value"].astype("float64")
    return long


def main() -> None:
    ap = argparse.ArgumentParser(description="因子表达式编译器（白名单 DSL）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-cols", help="列出可用列与算子")
    cp = sub.add_parser("compile", help="编译表达式并落盘")
    cp.add_argument("--name", required=True)
    cp.add_argument("--expr", required=True)
    cp.add_argument("--force", action="store_true")
    a = ap.parse_args()

    if a.cmd == "list-cols":
        print(json.dumps({"columns": feature_columns(), "ops": sorted(_OPS),
                          "max_window": MAX_WINDOW,
                          "banned": [c for c in wide_columns()
                                     if c not in feature_columns()]},
                         ensure_ascii=False))
        return

    p = alpha_dir() / f"{a.name}.parquet"
    if p.exists() and not a.force:
        print(json.dumps({"ok": False, "error": f"已存在 {p.name}（--force 覆盖）"},
                         ensure_ascii=False))
        raise SystemExit(1)
    try:
        long = compile_expr(a.name, a.expr)
    except CompileError as e:
        print(json.dumps({"ok": False, "name": a.name, "error": str(e)},
                         ensure_ascii=False))
        raise SystemExit(1)
    long.to_parquet(p, index=False)
    # 读回验证（纪律 1）：落盘后立刻读回核对范围
    back = pd.read_parquet(p)
    assert len(back) == len(long)
    print(json.dumps({
        "ok": True, "name": a.name, "expr": a.expr, "rows": len(long),
        "coverage": round(len(long) / (back["date"].nunique()
                                       * back["code"].nunique()), 4),
        "start": str(back["date"].min())[:10],
        "end": str(back["date"].max())[:10], "path": str(p),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
