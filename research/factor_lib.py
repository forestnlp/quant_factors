# -*- coding: utf-8 -*-
"""因子库（research 中间区）—— Loop 的「记忆」

闭环迭代的前提是有存量：所有生成过的因子（含失败与重复）一律入库，
才能做去重、失败回喂、产能与合格率统计。存储位置 data/factorlib.sqlite
（gitignore 区，不入库）。

表结构：
    factors   因子主表（expr_norm 唯一，作为去重键）
    metrics   指标表（factor_id × segment(full/is/oos) × neutral(0/1)）
    rounds    轮次表（每轮产出与三类比率统计）

用法：
    from research.factor_lib import FactorLib
    lib = FactorLib()
    lib.existing_exprs()            # 已存在表达式的规范化集合（去重用）
    lib.add_factor(...); lib.add_metrics(...)
    lib.stats()                     # 非法率 / 同质化率 / 合格率
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from research.config import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "factorlib.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS factors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    expr       TEXT NOT NULL,
    expr_norm  TEXT NOT NULL UNIQUE,
    logic      TEXT,
    status     TEXT NOT NULL,          -- valid / invalid / duplicate
    fail_reason TEXT,
    src        TEXT,                   -- llm / seed / manual
    round_id   INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metrics (
    factor_id  INTEGER NOT NULL,
    segment    TEXT NOT NULL,          -- full / is / oos
    neutral    INTEGER NOT NULL,       -- 0 原始截面 / 1 行业中性
    IC_mean    REAL, ICIR REAL,
    RankIC_mean REAL, RankICIR REAL,
    IC_positive_ratio REAL, n_days INTEGER,
    PRIMARY KEY (factor_id, segment, neutral),
    FOREIGN KEY (factor_id) REFERENCES factors(id)
);
CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    n_generated INTEGER, n_valid INTEGER,
    n_invalid INTEGER, n_duplicate INTEGER,
    note TEXT
);
"""

# 判定"有效因子"的门槛（样本外 + 中性后仍成立才算过）
VALID_RANKICIR = 0.20
OOS_KEEP_RATIO = 0.50


def normalize_expr(expr: str) -> str:
    """表达式规范化，作为去重键：去空白、统一大小写敏感字段名、排序无意义差异。

    只做保守规范化（空白与括号外空格），不做代数化简——同义改写
    （如 a/b 与 a*(1/b)）交给截面相关性去重那一层处理。
    """
    s = re.sub(r"\s+", "", expr or "")
    return s


class FactorLib:
    """因子库读写门面。"""

    def __init__(self, db_path: Path | None = None) -> None:
        self.path = Path(db_path or DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- 去重 ----------

    def existing_exprs(self) -> dict[str, int]:
        """返回 {规范化表达式: id}，覆盖所有历史因子（含失败与重复）。"""
        rows = self.conn.execute("SELECT expr_norm, id FROM factors").fetchall()
        return {r["expr_norm"]: r["id"] for r in rows}

    # ---------- 轮次 ----------

    def start_round(self, note: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO rounds (started_at, note) VALUES (?, ?)",
            (datetime.now().isoformat(timespec="seconds"), note))
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_round(self, round_id: int, n_generated: int, n_valid: int,
                     n_invalid: int, n_duplicate: int) -> None:
        self.conn.execute(
            "UPDATE rounds SET n_generated=?, n_valid=?, n_invalid=?, n_duplicate=? WHERE id=?",
            (n_generated, n_valid, n_invalid, n_duplicate, round_id))
        self.conn.commit()

    # ---------- 因子 ----------

    def add_factor(self, name: str, expr: str, logic: str, status: str,
                   round_id: int | None = None, src: str = "llm",
                   fail_reason: str | None = None) -> int | None:
        """写入一个因子；expr_norm 已存在则返回 None（视为重复，不覆盖历史）。"""
        norm = normalize_expr(expr)
        try:
            cur = self.conn.execute(
                "INSERT INTO factors (name, expr, expr_norm, logic, status,"
                " fail_reason, src, round_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (name, expr, norm, logic, status, fail_reason, src, round_id,
                 datetime.now().isoformat(timespec="seconds")))
            self.conn.commit()
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def mark_duplicate(self, name: str, expr: str, logic: str,
                       dup_of: int, round_id: int | None = None) -> None:
        """记录一个被判定为同质（相关系数过高）的因子。"""
        self.conn.execute(
            "INSERT OR IGNORE INTO factors (name, expr, expr_norm, logic, status,"
            " fail_reason, src, round_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (name, expr, normalize_expr(expr), logic, "duplicate",
             f"corr>threshold vs id={dup_of}", "llm", round_id,
             datetime.now().isoformat(timespec="seconds")))
        self.conn.commit()

    def add_metrics(self, factor_id: int, segment: str, neutral: bool,
                    m: dict) -> None:
        """写入一个因子在某切面/某处理下的指标。"""
        def f(k):
            v = m.get(k)
            return float(v) if v is not None and v == v else None

        self.conn.execute(
            "INSERT OR REPLACE INTO metrics (factor_id, segment, neutral,"
            " IC_mean, ICIR, RankIC_mean, RankICIR, IC_positive_ratio, n_days)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (factor_id, segment, int(neutral), f("IC_mean"), f("ICIR"),
             f("RankIC_mean"), f("RankICIR"), f("IC_positive_ratio"),
             int(m["n_days"]) if m.get("n_days") else None))
        self.conn.commit()

    # ---------- 负反馈：失败案例回喂 ----------

    def recent_failures(self, limit: int = 10) -> list[str]:
        """最近失败原因去重清单，用于注入下一轮 Prompt。"""
        rows = self.conn.execute(
            "SELECT DISTINCT fail_reason FROM factors"
            " WHERE status='invalid' AND fail_reason IS NOT NULL"
            " ORDER BY id DESC LIMIT ?", (limit * 3,)).fetchall()
        out = []
        for r in rows:
            s = str(r["fail_reason"]).split(":")[-1].strip()[:120]
            if s and s not in out:
                out.append(s)
            if len(out) >= limit:
                break
        return out

    def existing_logics(self, limit: int = 30) -> list[str]:
        """已有因子的逻辑摘要，用于提示模型避免同族。"""
        rows = self.conn.execute(
            "SELECT logic FROM factors WHERE logic IS NOT NULL"
            " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [r["logic"] for r in rows if r["logic"]]

    # ---------- 统计与查询 ----------

    def stats(self) -> dict:
        """产能与质量基线：非法率 / 同质化率 / 合格率。"""
        tot = self.conn.execute("SELECT COUNT(*) c FROM factors").fetchone()["c"]
        if not tot:
            return {"total": 0}
        by = {r["status"]: r["c"] for r in self.conn.execute(
            "SELECT status, COUNT(*) c FROM factors GROUP BY status")}
        passed = self.conn.execute(
            "SELECT COUNT(DISTINCT factor_id) c FROM metrics"
            " WHERE segment='oos' AND neutral=1 AND ABS(RankICIR) >= ?",
            (VALID_RANKICIR,)).fetchone()["c"]
        return {
            "total": tot,
            "valid": by.get("valid", 0),
            "invalid": by.get("invalid", 0),
            "duplicate": by.get("duplicate", 0),
            "invalid_rate": by.get("invalid", 0) / tot,
            "duplicate_rate": by.get("duplicate", 0) / tot,
            "pass_oos": passed,
            "pass_rate": passed / max(by.get("valid", 0), 1),
            "rounds": self.conn.execute("SELECT COUNT(*) c FROM rounds").fetchone()["c"],
        }

    def top_valid(self, n: int = 20) -> list[sqlite3.Row]:
        """按样本外中性后 |RankICIR| 排序的有效因子（堆顶原料）。"""
        return self.conn.execute(
            "SELECT f.id, f.name, f.expr, f.logic, m.RankICIR AS oos_neu_ricir"
            " FROM factors f JOIN metrics m ON m.factor_id=f.id"
            " WHERE f.status='valid' AND m.segment='oos' AND m.neutral=1"
            " ORDER BY ABS(m.RankICIR) DESC LIMIT ?", (n,)).fetchall()

    def close(self) -> None:
        self.conn.close()
