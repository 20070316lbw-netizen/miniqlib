# -*- coding: utf-8 -*-
"""
================================================================================
                    MiniQLib Phase B Unit Test: DataHandler & Sandbox
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

from mini_qlib.data.expression import Feature, MiniExpression
from mini_qlib.data.handler import DataHandler


class TestDataHandlerCompilation(unittest.TestCase):
    """
    Unit tests for compile-time path verification and error handling in DataHandler.
    """

    def setUp(self):
        dates = pd.date_range('2026-05-01', periods=3)
        self.df = pd.DataFrame({
            "close": [10.0, 11.0, 12.0],
            "open":  [9.5, 10.5, 11.5]
        }, index=dates)

    def test_compile_registry_keys(self):
        """DataHandler resolves registered feature keys such as KMID."""
        config = {
            "features": {
                "f1": "KMID"
            }
        }
        handler = DataHandler(self.df, config)
        self.assertIn("f1", handler.features)
        self.assertTrue(isinstance(handler.features["f1"], MiniExpression))

    def test_compile_custom_formula_string(self):
        """DataHandler dynamically parses and compiles customized math formula strings."""
        config = {
            "features": {
                "f2": "($close - $open) * 10"
            }
        }
        handler = DataHandler(self.df, config)
        self.assertIn("f2", handler.features)
        res = handler.setup()
        self.assertAlmostEqual(res["f2"].iloc[0], 5.0, places=5)

    def test_compile_invalid_formula_raises_valueerror(self):
        """DataHandler raises ValueError for syntactically invalid formulas."""
        config = {
            "features": {
                "f_bad": "Mean($close, 20"  # Missing closing bracket
            }
        }
        with self.assertRaises(ValueError):
            DataHandler(self.df, config)

    def test_compile_unsupported_type_raises_typeerror(self):
        """DataHandler raises TypeError for unsupported input object types."""
        config = {
            "features": {
                "f_bad": 12345  # Not a string, nor a MiniExpression
            }
        }
        with self.assertRaises(TypeError):
            DataHandler(self.df, config)


class TestDataHandlerEvalSandbox(unittest.TestCase):
    """
    Security regression tests validating that the custom eval sandbox is strictly locked down.
    """

    def setUp(self):
        dates = pd.date_range('2026-05-01', periods=3)
        self.df = pd.DataFrame({"close": [10.0, 11.0, 12.0]}, index=dates)

    def test_eval_blocks_builtins(self):
        """The eval sandbox blocks standard Python built-ins like __import__."""
        # Standard exploit: trying to import os and run command
        config = {
            "features": {
                "exploit": "__import__('os').system('whoami')"
            }
        }
        with self.assertRaises(ValueError) as ctx:
            DataHandler(self.df, config)
        self.assertIn("name '__import__' is not defined", str(ctx.exception))

    def test_eval_blocks_open(self):
        """The eval sandbox blocks built-in open function to prevent file leaks."""
        config = {
            "features": {
                "exploit": "open('config.yaml', 'r').read()"
            }
        }
        with self.assertRaises(ValueError) as ctx:
            DataHandler(self.df, config)
        self.assertIn("name 'open' is not defined", str(ctx.exception))

    def test_eval_blocks_eval_nesting(self):
        """The eval sandbox blocks nested eval calls."""
        config = {
            "features": {
                "exploit": "eval('1 + 1')"
            }
        }
        with self.assertRaises(ValueError) as ctx:
            DataHandler(self.df, config)
        self.assertIn("name 'eval' is not defined", str(ctx.exception))


class TestDataHandlerSetup(unittest.TestCase):
    """
    Tests for end-to-end factor compilation matrix setup and caching.
    """

    def test_setup_preserves_multiindex_and_caching(self):
        """setup() generates properly aligned panel outputs and shares context cache."""
        dates = pd.date_range('2026-05-01', periods=3)
        tickers = ['AAPL', 'MSFT']
        index = pd.MultiIndex.from_product([dates, tickers], names=['date', 'ticker'])
        
        df = pd.DataFrame({
            "close": [100.0, 200.0, 101.0, 202.0, 102.0, 203.0],
            "open":  [98.0, 195.0, 99.0, 198.0, 100.0, 201.0]
        }, index=index)
        
        config = {
            "features": {
                "MY_KMID": "KMID",
                "MY_MA5": "MA5"
            }
        }
        
        handler = DataHandler(df, config)
        context = {}
        res = handler.setup(context=context)
        
        # Output holds correct column names
        self.assertEqual(set(res.columns), {"MY_KMID", "MY_MA5"})
        # Keeps original MultiIndex structure
        pd.testing.assert_index_equal(res.index, df.index)
        # Context populated with unique cache keys
        self.assertTrue(len(context) > 0)
        self.assertIn("$close", context)


if __name__ == "__main__":
    print("🎬 开始运行 DataHandler 编译器与沙箱安全自动化单元测试...")
    unittest.main()
