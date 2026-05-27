# -*- coding: utf-8 -*-
"""
================================================================================
                    MiniQLib Phase C Unit Test: Backtest Integration
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

from mini_qlib.backtest.data_portal import DataPortal
from mini_qlib.backtest.blotter import Order, Blotter, Position
from mini_qlib.backtest.exchange import Exchange
from mini_qlib.backtest.backtest import run_backtest


class TestBacktestIntegration(unittest.TestCase):
    """
    Integration tests for event-driven backtest loops, ledger and exchange matchers.
    """

    def setUp(self):
        records = [
            {"date": "2026-05-01", "ticker": "AAPL", "open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": 1000.0},
            {"date": "2026-05-01", "ticker": "MSFT", "open": 200.0, "high": 205.0, "low": 198.0, "close": 202.0, "volume": 500.0},
            {"date": "2026-05-02", "ticker": "AAPL", "open": 103.0, "high": 108.0, "low": 101.0, "close": 106.0, "volume": 2000.0},
            {"date": "2026-05-02", "ticker": "MSFT", "open": 203.0, "high": 208.0, "low": 201.0, "close": 206.0, "volume": 800.0},
            {"date": "2026-05-03", "ticker": "AAPL", "open": 105.0, "high": 110.0, "low": 104.0, "close": 108.0, "volume": 1500.0},
            {"date": "2026-05-03", "ticker": "MSFT", "open": 205.0, "high": 210.0, "low": 204.0, "close": 208.0, "volume": 600.0},
        ]
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        self.market_data = df.set_index(["date", "ticker"]).sort_index()

    def test_full_cycle_two_stocks_two_days(self):
        """End-to-end event backtest run with K=1 rotation executes perfectly."""
        # Setup mock predictions for AAPL and MSFT
        # Day 1: AAPL high score (1.0), MSFT low score (0.0) -> Buy AAPL
        # Day 2: MSFT high score (2.0), AAPL low score (-1.0) -> Sell AAPL, Buy MSFT
        # Day 3: AAPL high score (3.0), MSFT low score (0.0) -> Sell MSFT, Buy AAPL
        pred_records = [
            {"date": "2026-05-01", "ticker": "AAPL", "score": 1.0},
            {"date": "2026-05-01", "ticker": "MSFT", "score": 0.0},
            {"date": "2026-05-02", "ticker": "AAPL", "score": -1.0},
            {"date": "2026-05-02", "ticker": "MSFT", "score": 2.0},
            {"date": "2026-05-03", "ticker": "AAPL", "score": 3.0},
            {"date": "2026-05-03", "ticker": "MSFT", "score": 0.0},
        ]
        pred_df = pd.DataFrame(pred_records)
        pred_df["date"] = pd.to_datetime(pred_df["date"])
        predictions = pred_df.set_index(["date", "ticker"])["score"]

        # Run the backtester
        history_df = run_backtest(
            df=self.market_data,
            predictions=predictions,
            initial_cash=10000.0,
            K=1,
            max_volume_ratio=0.5,
            slippage=0.0,
            fee_rate=0.0,
            tax_rate=0.0
        )

        self.assertEqual(len(history_df), 3)
        # NAV should start at 10000.0
        self.assertEqual(history_df["nav"].iloc[0], 10000.0)

    def test_sell_stamp_tax_applied(self):
        """Sell order applies stamp duty tax correctly to transaction log."""
        portal = DataPortal(self.market_data)
        blotter = Blotter(initial_cash=10000.0)
        
        t1 = pd.Timestamp("2026-05-01")
        t2 = pd.Timestamp("2026-05-02")
        
        # Submitting buy order first
        order_buy = Order("B01", "AAPL", "BUY", 10, t1)
        blotter.submit_order(order_buy)
        Exchange.match_orders(blotter, t2, portal, slippage=0.0, fee_rate=0.0, tax_rate=0.0)
        
        # Verify hold AAPL
        self.assertEqual(blotter.positions["AAPL"].volume, 10.0)
        
        # Submit sell order with 0.1% stamp tax and 0.2% commission
        order_sell = Order("S01", "AAPL", "SELL", 10, t2)
        blotter.submit_order(order_sell)
        
        t3 = pd.Timestamp("2026-05-03")
        Exchange.match_orders(
            blotter=blotter,
            current_date=t3,
            data_portal=portal,
            max_volume_ratio=1.0,
            slippage=0.0,
            fee_rate=0.002,  # 0.2% commission
            tax_rate=0.001   # 0.1% stamp duty
        )
        
        # AAPL on T3 has open=105.0. 10 shares * 105 = 1050 USD principal.
        # Sell expenses: 0.2% commission (2.1) + 0.1% tax (1.05) = 3.15 USD
        # Net received cash = 1050 - 3.15 = 1046.85 USD
        self.assertEqual(blotter.positions.get("AAPL"), None) # Position cleared
        
        trade = next(t for t in blotter.trade_history if t["order_id"] == "S01")
        self.assertAlmostEqual(trade["commission"], 3.15, places=5)

    def test_nav_calculation_with_suspended_stock(self):
        """Blotter falls back to weighted average cost price for suspended assets (NaN price)."""
        blotter = Blotter(initial_cash=5000.0)
        
        # Manually inject position with average cost = 100.0
        blotter.positions["AAPL"] = Position("AAPL")
        blotter.positions["AAPL"].volume = 20.0
        blotter.positions["AAPL"].cost_price = 100.0
        
        # AAPL price is NaN (representing suspended stock)
        current_prices = {"AAPL": float("nan")}
        
        # Net Asset Value = Cash (5000) + Holding at cost (20 * 100 = 2000) = 7000.0
        nav = blotter.get_nav(current_prices)
        self.assertEqual(nav, 7000.0)


if __name__ == "__main__":
    print("🎬 开始运行事件驱动回测引擎集成自动化测试...")
    unittest.main()
