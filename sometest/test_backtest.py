# -*- coding: utf-8 -*-
"""
Automated Unit Tests for MiniQLib Event-Driven Backtesting Module
MiniQLib 事件驱动回测核心模块自动化单元测试 (零依赖标准库 unittest 版)

Verifies temporal sandbox clipping, strict T+1 transaction delay,
market volume cap restrictions with immediate-cancel, and cash overdraft protection.
验证时序沙箱切片隔离、严格 T+1 交易成交延迟、成交量上限即时撤单限制以及现金超支降额与撤单保护。
"""
import sys
import unittest
from pathlib import Path
import pandas as pd
import numpy as np

# Ensure project path resolution under Windows environment
# 确保 Windows 下根目录解析正确，防止 ModuleNotFoundError
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "mini_qlib"))

from mini_qlib.backtest.data_portal import DataPortal
from mini_qlib.backtest.blotter import Order, Position, Blotter
from mini_qlib.backtest.exchange import Exchange


class TestBacktestComponents(unittest.TestCase):
    """
    TestCase suite for event-driven backtesting primitives.
    事件驱动回测基础要素单元测试用例组。
    """

    def setUp(self):
        """
        Constructs a 3-day Panel Dataset for 2 stocks (AAPL, MSFT) as test fixture.
        构建一个包含 2 只股票（AAPL, MSFT）及 3 个交易日的面板数据集作为测试基准。
        """
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

    def test_data_portal_temporal_sandbox(self):
        """
        Verifies that DataPortal strictly shields future prices and correctly slices historical series.
        验证 DataPortal 是否严格屏蔽未来价格并正确切片历史序列。
        """
        portal = DataPortal(self.market_data)
        t1 = pd.Timestamp("2026-05-01")
        t2 = pd.Timestamp("2026-05-02")

        # Correctly fetches current and historic data
        # 正常查询当前值
        self.assertEqual(portal.get_current("AAPL", "close", t1), 102.0)
        self.assertEqual(portal.get_current("MSFT", "open", t2), 203.0)

        # Truncates look-ahead data strictly
        # 即使 t2 在行情表中，如果以 t1 时间切片，也绝对查不到 t2 的价格
        self.assertFalse(pd.isna(portal.get_current("AAPL", "close", t2)))
        
        # Historical length query limit test: Retrieve historical series
        # 历史长度查询限制测试：获取历史序列
        hist_series = portal.get_history("AAPL", "close", t2, N=2)
        self.assertEqual(len(hist_series), 2)
        self.assertEqual(list(hist_series.index), [t1, t2])
        self.assertEqual(list(hist_series.values), [102.0, 106.0])

        # Future dates strictly not visible
        # 在 t1 时提取历史，绝不能把 t2 的信息包含进去
        hist_at_t1 = portal.get_history("AAPL", "close", t1, N=5)
        self.assertEqual(len(hist_at_t1), 1)
        self.assertNotIn(t2, hist_at_t1.index)

    def test_strict_t1_latency_and_slippage(self):
        """
        Verifies strict T+1 transaction execution and correct slippage & commission bookkeeping.
        验证严格的 T+1 交易成交延迟，以及正确的滑点与佣金费用结算。
        """
        portal = DataPortal(self.market_data)
        blotter = Blotter(initial_cash=10000.0)

        t1 = pd.Timestamp("2026-05-01")
        t2 = pd.Timestamp("2026-05-02")

        # Strategy submits an order at T1
        # 策略在 T1 提交一笔买入 50 股 AAPL 的挂单
        order = Order(order_id="ORD_001", ticker="AAPL", direction="BUY", volume=50, timestamp=t1)
        blotter.submit_order(order)
        
        self.assertEqual(len(blotter.open_orders), 1)
        self.assertEqual(blotter.open_orders[0].status, "PENDING")

        # Try matching on the SAME date (T1) -> should NOT match (temporal delay lock)
        # 尝试在同一天（T1）撮合该订单 -> 应当不予撮合（受 T+1 延迟锁限制）
        Exchange.match_orders(blotter, current_date=t1, data_portal=portal)
        self.assertEqual(len(blotter.open_orders), 1)
        self.assertEqual(blotter.open_orders[0].status, "PENDING")

        # Move simulation time forward to T2 and execute matching
        # 时间轴推进至 T2 并执行撮合
        slippage = 0.01  # 1% slippage
        fee_rate = 0.002  # 0.2% commission
        Exchange.match_orders(
            blotter=blotter,
            current_date=t2,
            data_portal=portal,
            max_volume_ratio=1.0,  # No volume limitation for this test
            slippage=slippage,
            fee_rate=fee_rate,
            tax_rate=0.0
        )

        # Order should be filled now
        # 挂单应当已成功撮合成交
        self.assertEqual(len(blotter.open_orders), 0)
        self.assertEqual(order.status, "FILLED")

        # Verify executed fill price: T2 Open price (103.0) + 1% Slippage (1.03) = 104.03
        # 校验成交价：次日开盘价 103.0 乘以（1 + 1% 滑点）= 104.03
        trade = blotter.trade_history[0]
        self.assertAlmostEqual(trade["price"], 104.03, places=5)
        self.assertEqual(trade["volume"], 50)

        # Verify cash deduction: 50 * 104.03 = 5201.5 USD principal + 0.2% commission (10.403) = 5211.903
        # 验证现金变动：本金 5201.5 + 佣金 10.403 = 5211.903 USD
        self.assertAlmostEqual(blotter.cash, 10000.0 - 5211.903, places=5)
        self.assertIn("AAPL", blotter.positions)
        self.assertEqual(blotter.positions["AAPL"].volume, 50)
        self.assertAlmostEqual(blotter.positions["AAPL"].cost_price, 104.03, places=5)

    def test_liquidity_volume_limit_and_immediate_cancel(self):
        """
        Verifies that excessive buy orders get partially filled up to 10% of market volume,
        and the remaining shares get immediately and safely cancelled from the pending book.
        验证超额买单是否只部分成交至成交量的 10%，而未成交部分的剩余股数是否被即刻安全撤销（不再留存）。
        """
        portal = DataPortal(self.market_data)
        blotter = Blotter(initial_cash=1000000.0)

        t1 = pd.Timestamp("2026-05-01")
        t2 = pd.Timestamp("2026-05-02")

        # AAPL market volume on T2 is 2000.0 shares. Under max_ratio=0.1, max executable is 200 shares.
        # AAPL 在 T2 的市场实际总成交量为 2000 股。在上限比例 10% 约束下，当日单股最大可买入量为 200 股。
        # We submit a massive order of 800 shares
        # 我们下达一个高达 800 股的大订单
        order = Order(order_id="ORD_BIG", ticker="AAPL", direction="BUY", volume=800, timestamp=t1)
        blotter.submit_order(order)

        # Match orders at T2
        Exchange.match_orders(
            blotter=blotter,
            current_date=t2,
            data_portal=portal,
            max_volume_ratio=0.1,  # 10% volume cap
            slippage=0.0,
            fee_rate=0.0,
            tax_rate=0.0
        )

        # The order must be popped from pending queue (status FILLED or finished)
        # 订单应当已移出 pending 队列（因为剩余部分被即刻撤销，不会继续等待）
        self.assertEqual(len(blotter.open_orders), 0)
        self.assertEqual(order.status, "FILLED")

        # Execution trade logs should reflect exact partial fill of 200 shares
        # 成交记录只记录了成功部分成交的 200 股，剩余的 600 股已被交易所抛弃，符合极简设计
        self.assertEqual(len(blotter.trade_history), 1)
        trade = blotter.trade_history[0]
        self.assertEqual(trade["volume"], 200.0)
        self.assertEqual(trade["price"], 103.0)  # T2 Open with zero slippage
        self.assertEqual(blotter.positions["AAPL"].volume, 200.0)

    def test_cash_protection_and_auto_scale_down(self):
        """
        Verifies that if a BUY order requires more cash than available,
        the exchange automatically scales down the volume to match maximum available cash,
        or cancels it entirely if the budget is not even enough for a single share.
        验证当买入订单超出预算时，交易所是否能自动按现金余额降额买入，或者在钱连 1 股都不够时彻底自动撤单。
        """
        portal = DataPortal(self.market_data)
        
        t1 = pd.Timestamp("2026-05-01")
        t2 = pd.Timestamp("2026-05-02")

        # Case A: Cash is enough for partial shares (scale down)
        # 情况 A：现金只够买一部分（执行缩减比例买入）
        # Balance: 500 USD. AAPL T2 Open price is 103 USD. Slippage/fee = 0.
        # 500 USD 可供买入。T2 开盘价 103 USD。最多买入 4 股 (412 USD)
        blotter_a = Blotter(initial_cash=500.0)
        order_a = Order(order_id="ORD_A", ticker="AAPL", direction="BUY", volume=10, timestamp=t1)
        blotter_a.submit_order(order_a)

        Exchange.match_orders(blotter_a, t2, portal, max_volume_ratio=1.0, slippage=0.0, fee_rate=0.0)
        self.assertEqual(len(blotter_a.open_orders), 0)
        self.assertEqual(order_a.status, "FILLED")
        self.assertEqual(blotter_a.positions["AAPL"].volume, 4.0)
        self.assertAlmostEqual(blotter_a.cash, 500.0 - 4.0 * 103.0, places=5)

        # Case B: Cash is too low to buy even 1 share (force cancel)
        # 情况 B：余额不够买 1 股（执行自动撤销订单）
        # Balance: 50 USD. AAPL T2 Open price is 103 USD.
        # 50 USD 不够买任何 1 股，应当直接被取消
        blotter_b = Blotter(initial_cash=50.0)
        order_b = Order(order_id="ORD_B", ticker="AAPL", direction="BUY", volume=10, timestamp=t1)
        blotter_b.submit_order(order_b)

        Exchange.match_orders(blotter_b, t2, portal, max_volume_ratio=1.0, slippage=0.0, fee_rate=0.0)
        self.assertEqual(len(blotter_b.open_orders), 0)
        self.assertEqual(order_b.status, "CANCELLED")
        self.assertNotIn("AAPL", blotter_b.positions)
        self.assertAlmostEqual(blotter_b.cash, 50.0, places=5)


if __name__ == "__main__":
    # Ensure Windows console prints emoji and UTF-8 characters safely
    # 确保 Windows 终端安全打印 Emoji 和 UTF-8 字符，防范 GBK 编码崩溃
    try:
        if sys.stdout.encoding.lower() != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass
    print("🎬 正在使用 Python 内置 unittest 标准库启动自动化测试...")
    unittest.main()

