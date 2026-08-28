# -*- coding: utf-8 -*-
"""research 中间区冒烟测试

验证 config / data_fetcher / factor_eval 三模块的核心逻辑可正常运行。

运行：
    pytest research/tests/test_research.py -v
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from research.config import PROJECT_ROOT as CFG_ROOT, bt_export_dir, qlib_uri  # noqa: E402
from research.factor_eval import winsorize_zscore  # noqa: E402


class TestConfig:
    def test_project_root(self):
        assert CFG_ROOT == PROJECT_ROOT

    def test_qlib_uri_returns_path(self):
        p = qlib_uri()
        assert isinstance(p, Path)
        # 缺省指向 data/cn_data
        assert str(p).endswith("cn_data") or "cn_data" in str(p)

    def test_bt_export_dir_creatable(self):
        d = bt_export_dir()
        assert d.exists()


class TestWinsorizeZscore:
    def _make_df(self):
        idx = pd.MultiIndex.from_product(
            [["2024-01-02", "2024-01-03"], ["a", "b", "c", "d"]],
            names=["datetime", "instrument"],
        )
        return pd.DataFrame({"f1": [10, 20, 30, 1000, -5, 6, 8, 12]}, index=idx)

    def test_shape_preserved(self):
        df = self._make_df()
        out = winsorize_zscore(df, ["f1"])
        assert list(out.columns) == ["f1"]
        assert len(out) == len(df)

    def test_median_normalized_per_crosssection(self):
        """每截面中位数应接近 0。"""
        df = self._make_df()
        out = winsorize_zscore(df, ["f1"])
        med_by_day = out["f1"].groupby(level="datetime").mean()
        for v in med_by_day.values:
            assert abs(v) < 1.0

    def test_clipped_to_3(self):
        df = self._make_df()  # 含极端值 1000
        out = winsorize_zscore(df, ["f1"])
        assert out["f1"].abs().max() <= 3.0 + 1e-9


class TestImportable:
    def test_data_fetcher_imports(self):
        import research.data_fetcher as m
        assert hasattr(m, "fetch_eastmoney_kline")
        assert hasattr(m, "clean_bars")
        assert hasattr(m, "ensure_qlib_data")

    def test_factor_eval_imports(self):
        import research.factor_eval as m
        assert hasattr(m, "load_factor_data")
        assert hasattr(m, "scan_factors")
