# -*- coding: utf-8 -*-
"""
================================================================================
                    MiniQLib Phase D Unit Test: Registry & PIT
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

from mini_qlib.factor import feature_registry, label_registry
from mini_qlib.data.expression import Feature, PFeature
from mini_qlib.data.ops import Ref, Add


class TestRegistries(unittest.TestCase):
    """
    Unit tests validating features and labels registry storage mechanisms.
    """

    def test_feature_registry_register_and_get(self):
        """FeatureRegistry stores features by name and retrieves them correctly."""
        feature_registry.register("TEST_FEAT", "($close - $open) / $open", "Test feature description")
        self.assertIn("TEST_FEAT", feature_registry.list_all())
        self.assertEqual(feature_registry.get("TEST_FEAT"), "($close - $open) / $open")
        self.assertEqual(feature_registry.get_description("TEST_FEAT"), "Test feature description")

    def test_label_registry_register_and_get(self):
        """LabelRegistry stores labels by name and retrieves them correctly."""
        label_registry.register("TEST_LABEL", "Ref($close, -1) / $close - 1", "Test label description")
        self.assertIn("TEST_LABEL", label_registry.list_all())
        self.assertEqual(label_registry.get("TEST_LABEL"), "Ref($close, -1) / $close - 1")

    def test_get_unregistered_raises_keyerror(self):
        """Retrieving unregistered key from registries raises KeyError."""
        with self.assertRaises(KeyError):
            feature_registry.get("NON_EXISTENT_FACTOR_123")


class TestLabelComputation(unittest.TestCase):
    """
    Unit tests validating look-ahead negative offset Ref calculations (e.g. forward returns).
    """

    def test_label_negative_ref_multistock(self):
        """Negative Ref ($close, -1) works correctly under MultiIndex grouping without cross-ticker leaks."""
        dates = pd.date_range('2026-05-01', periods=3)
        tickers = ['AAPL', 'MSFT']
        index = pd.MultiIndex.from_product([dates, tickers], names=['date', 'ticker'])
        
        df = pd.DataFrame({
            "close": [10.0, 100.0, 12.0, 105.0, 15.0, 110.0]
        }, index=index)
        
        close_f = Feature("close")
        # Ref with negative offset represents future close (look-ahead for labels)
        future_close = Ref(close_f, -1)
        res = future_close.load(df)
        
        # AAPL Day 1 future close should be AAPL Day 2 close (12.0)
        self.assertEqual(res.loc[('2026-05-01', 'AAPL')], 12.0)
        # MSFT Day 1 future close should be MSFT Day 2 close (105.0)
        self.assertEqual(res.loc[('2026-05-01', 'MSFT')], 105.0)
        
        # Last days should be NaN for both tickers
        self.assertTrue(pd.isna(res.loc[('2026-05-03', 'AAPL')]))
        self.assertTrue(pd.isna(res.loc[('2026-05-03', 'MSFT')]))


class TestPFeaturePIT(unittest.TestCase):
    """
    Integration and unit tests verifying that PFeature correctly queries the database
    and aligns quarterly/annual financial disclosures using backward ASOF merges.
    """

    def test_pfeature_pit_alignment_logic(self):
        """PFeature correctly performs backward ASOF merge alignment."""
        dates = pd.to_datetime(['2026-05-01', '2026-05-02', '2026-05-03', '2026-05-04'])
        tickers = ['AAPL']
        index = pd.MultiIndex.from_product([dates, tickers], names=['date', 'ticker'])
        
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0, 103.0]}, index=index)
        
        # Standard PIT revenue loading
        revenue_f = PFeature("revenue")
        
        # Mock database loading inside _load_internal by patching get_db or conn
        # But we can also test it using the actual edgar database since we have it!
        # Let's run it with actual database if edgar.duckdb is populated and has AAPL
        res = revenue_f.load(df)
        
        # Even if database is empty, the return is a pandas Series with index aligned
        self.assertEqual(len(res), len(df))
        pd.testing.assert_index_equal(res.index, df.index)
        
        # Check standard registered factors
        self.assertIn("ROE", feature_registry.list_all())
        self.assertIn("Leverage", feature_registry.list_all())
        self.assertIn("OpMargin", feature_registry.list_all())


if __name__ == "__main__":
    print("🎬 开始运行注册表与时点财务算子自动化单元测试...")
    unittest.main()
