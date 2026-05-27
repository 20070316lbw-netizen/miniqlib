# -*- coding: utf-8 -*-
"""
================================================================================
                    MiniQLib Phase A Unit Test: Operators Edge Cases
================================================================================
"""
import sys
import unittest
from pathlib import Path
import pandas as pd
import numpy as np

# Ensure Windows prints emoji safely
try:
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, OSError):
    pass

# Project root pathing
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "mini_qlib"))

from mini_qlib.data.expression import Feature
from mini_qlib.data.ops import Log, Sign, Abs, If, Add, Greater, Less


class TestSingleOperators(unittest.TestCase):
    """
    Unit tests for single element-wise operators boundaries.
    """

    def test_log_negative_handles_nan(self):
        """Log handles negative/zero values by returning NaN without raising exceptions."""
        dates = pd.date_range('2026-05-01', periods=3)
        df = pd.DataFrame({"close": [10.0, 0.0, -5.0]}, index=dates)
        
        close_f = Feature("close")
        log_expr = Log(close_f)
        res = log_expr.load(df)
        
        self.assertAlmostEqual(res.iloc[0], np.log(10.0), places=5)
        self.assertTrue(pd.isna(res.iloc[1]))
        self.assertTrue(pd.isna(res.iloc[2]))

    def test_sign_zero_returns_zero(self):
        """Sign(0) returns 0 correctly."""
        dates = pd.date_range('2026-05-01', periods=3)
        df = pd.DataFrame({"close": [5.0, 0.0, -3.0]}, index=dates)
        
        close_f = Feature("close")
        sign_expr = Sign(close_f)
        res = sign_expr.load(df)
        
        self.assertEqual(res.iloc[0], 1.0)
        self.assertEqual(res.iloc[1], 0.0)
        self.assertEqual(res.iloc[2], -1.0)

    def test_abs_negative_returns_positive(self):
        """Abs returns positive values for negative inputs."""
        dates = pd.date_range('2026-05-01', periods=3)
        df = pd.DataFrame({"close": [-10.5, 0.0, 5.5]}, index=dates)
        
        close_f = Feature("close")
        abs_expr = Abs(close_f)
        res = abs_expr.load(df)
        
        self.assertEqual(res.iloc[0], 10.5)
        self.assertEqual(res.iloc[1], 0.0)
        self.assertEqual(res.iloc[2], 5.5)


class TestIfOperator(unittest.TestCase):
    """
    Unit tests for the tri-wise If operator condition branch routing.
    """

    def test_if_condition_true_false_routing(self):
        """If operator routes to left when true and right when false."""
        dates = pd.date_range('2026-05-01', periods=4)
        df = pd.DataFrame({
            "cond":  [True, False, True, False],
            "left":  [100.0, 200.0, 300.0, 400.0],
            "right": [-1.0, -2.0, -3.0, -4.0]
        }, index=dates)
        
        cond_f = Feature("cond")
        left_f = Feature("left")
        right_f = Feature("right")
        
        if_expr = If(cond_f, left_f, right_f)
        res = if_expr.load(df)
        
        self.assertEqual(res.iloc[0], 100.0)
        self.assertEqual(res.iloc[1], -2.0)
        self.assertEqual(res.iloc[2], 300.0)
        self.assertEqual(res.iloc[3], -4.0)

    def test_if_mixed_scalar_series(self):
        """If operator aligns properly when mixing scalar constants and series."""
        dates = pd.date_range('2026-05-01', periods=3)
        df = pd.DataFrame({
            "cond": [True, False, True],
            "close": [10.0, 20.0, 30.0]
        }, index=dates)
        
        cond_f = Feature("cond")
        close_f = Feature("close")
        
        if_expr = If(cond_f, close_f, 999.0)  # mixed series + scalar
        res = if_expr.load(df)
        
        self.assertEqual(res.iloc[0], 10.0)
        self.assertEqual(res.iloc[1], 999.0)
        self.assertEqual(res.iloc[2], 30.0)


class TestNpPairOperatorMultiStock(unittest.TestCase):
    """
    Unit tests for NpPairOperator under a MultiIndex Panel Data setting.
    """

    def test_add_two_stocks_alignment(self):
        """Add and Greater/Less operators work and align correctly under MultiIndex."""
        dates = pd.date_range('2026-05-01', periods=2)
        tickers = ['AAPL', 'MSFT']
        index = pd.MultiIndex.from_product([dates, tickers], names=['date', 'ticker'])
        
        df = pd.DataFrame({
            "open":  [10.0, 20.0, 11.0, 21.0],
            "close": [15.0, 18.0, 12.0, 25.0]
        }, index=index)
        
        open_f = Feature("open")
        close_f = Feature("close")
        
        # 1. Test Add
        add_expr = Add(open_f, close_f)
        res_add = add_expr.load(df)
        self.assertEqual(res_add.loc[('2026-05-01', 'AAPL')], 25.0)
        self.assertEqual(res_add.loc[('2026-05-01', 'MSFT')], 38.0)
        
        # 2. Test Greater & Less maximum/minimum element-wise
        greater_expr = Greater(open_f, close_f)
        res_gt = greater_expr.load(df)
        self.assertEqual(res_gt.loc[('2026-05-01', 'AAPL')], 15.0) # max(10, 15)
        self.assertEqual(res_gt.loc[('2026-05-01', 'MSFT')], 20.0) # max(20, 18)
        
        less_expr = Less(open_f, close_f)
        res_lt = less_expr.load(df)
        self.assertEqual(res_lt.loc[('2026-05-01', 'AAPL')], 10.0) # min(10, 15)
        self.assertEqual(res_lt.loc[('2026-05-01', 'MSFT')], 18.0) # min(20, 18)


if __name__ == "__main__":
    print("🎬 开始运行单算子与边界值自动化单元测试...")
    unittest.main()
