# -*- coding: utf-8 -*-
"""
Backtest Loop: Event-Driven Simulation Engine and Alpha Strategy Executor
Backtest Loop: 事件驱动回测引擎与阿尔法策略执行器

Drives the daily bar-by-bar progression, triggers the Exchange matcher,
calculates portfolio valuation (NAV), and coordinates the Top-K equal-weight rotation strategy.
驱动每日 Bar 的不可逆递进、触发交易所撮合器、计算投资组合估值（NAV），并协调 Top-K 等权重轮动阿尔法策略。
"""
from typing import Optional, Dict, Any, List
import pandas as pd
import numpy as np

from .data_portal import DataPortal
from .blotter import Order, Blotter
from .exchange import Exchange
from mini_qlib.utils.log import get_logger

_log = get_logger(__name__)


def run_backtest(
    df: pd.DataFrame,
    predictions: Optional[pd.Series] = None,
    initial_cash: float = 1000000.0,
    K: int = 5,
    max_volume_ratio: float = 0.1,
    slippage: float = 0.0005,
    fee_rate: float = 0.0003,
    tax_rate: float = 0.001,
    strategy: Optional[Any] = None,
) -> pd.DataFrame:
    """
    Run high-fidelity event-driven backtesting for a Top-K rotation strategy on test predictions.
    对测试集预测值执行高保真的事件驱动回测，跑通 Top-K 等权重轮动选股策略。

    Parameters / 参数:
        df (pd.DataFrame): Sorted market price MultiIndex dataset (date, ticker) containing ['open', 'close', 'volume'].
                           排好序的多股票 MultiIndex 行情数据，必须包含开盘价、收盘价和成交量。
        predictions (pd.Series): Predicted scores mapping to MultiIndex (date, ticker) indexes on the test set.
                                 测试集上的因子预测得分，其索引为相同的 ['date', 'ticker']。
        initial_cash (float): Starting trading balance / 初始账户现金余额。
        K (int): Number of top scoring stocks to hold equally / 每日做多等权重的排名前 K 只股票数量。
        max_volume_ratio (float): Exchange liquidity cap ratio / 交易所成交量占比限制上限。
        slippage (float): Spread friction penalty / 撮合滑点率。
        fee_rate (float): Trading commission cost rate / 交易经手费佣金率。
        tax_rate (float): Stamp duty tax rate on SELL orders / 卖出印花税率。

    Returns / 返回:
        pd.DataFrame: Portfolio performance series index by date containing ['nav', 'cash'].
                      每日资金账簿净值报表，包含净资产 ['nav'] 与现金余额 ['cash']，以 date 为索引。
    """
    _log.info("正在初始化事件驱动回测引擎 (Event-driven Backtest initialization)...")
    _log.info("   [账户初始资金] %s USD | [选股做多数量 K] %d 只", f"{initial_cash:,.2f}", K)
    _log.info("   [撮合延迟规则] 严格 T+1 延迟 | [成交上限 max_ratio] %.1f%% 成交量", max_volume_ratio * 100)

    # 1. Core ledger and data gateway initialization
    # 初始化核心分类账簿与只读高性能行情沙箱网关
    data_portal = DataPortal(df)
    blotter = Blotter(initial_cash)

    # Initialize strategy if not provided (defaulting to TopK equal weight rotation)
    if strategy is None:
        from .strategy import TopKRotationStrategy
        strategy = TopKRotationStrategy(K=K)

    # Extract sorted chronology of trading days. If predictions are not available, use all unique dates in the market dataset.
    if predictions is not None:
        backtest_dates = predictions.index.get_level_values("date").unique().sort_values()
    else:
        backtest_dates = df.index.get_level_values("date").unique().sort_values()

    # Trackers to store portfolio history for analytics
    # 历史记录列表，最终用于生成每日净值时序 DataFrame
    history_records = []

    # 2. Main Event Loop (Bar-by-Bar chronological simulation)
    # 主事件循环（日频 Bar 不可逆物理轴推进）
    for day_idx, current_date in enumerate(backtest_dates):
        # ----------------------------------------------------------------------
        # Step A: Trigger simulated Exchange matching for pending orders
        # 步骤 A：启动仿真交易所撮合上一个交易日挂起的 PENDING 订单
        # ----------------------------------------------------------------------
        if len(blotter.open_orders) > 0:
            Exchange.match_orders(
                blotter=blotter,
                current_date=current_date,
                data_portal=data_portal,
                max_volume_ratio=max_volume_ratio,
                slippage=slippage,
                fee_rate=fee_rate,
                tax_rate=tax_rate,
            )

        # ----------------------------------------------------------------------
        # Step B: Value Portfolio holdings and calculate current NAV
        # 步骤 B：盘点持仓估值，计算今日收盘资产净值 NAV
        # ----------------------------------------------------------------------
        current_prices = {}
        for ticker in list(blotter.positions.keys()):
            close_price = data_portal.get_current(ticker, "close", current_date)
            # Use current close for valuation. If missing (e.g. suspended), fallback to cost
            # 提取今日收盘价做市值折合，如遇不可得（停牌等），底层自动安全回退为持仓成本价
            current_prices[ticker] = close_price if not pd.isna(close_price) else blotter.positions[ticker].cost_price

        # Update NAV (Cash + holdings value)
        # 获取今日账户实时资产净值
        nav = blotter.get_nav(current_prices)

        # ----------------------------------------------------------------------
        # Step C: Strategy Decision Making (Decoupled strategy class execution)
        # 步骤 C：执行策略决策（解耦后的可插拔交易策略触发）
        # ----------------------------------------------------------------------
        orders = strategy.on_bar(
            current_date=current_date,
            data_portal=data_portal,
            blotter=blotter,
            nav=nav,
            predictions=predictions,
        )
        for order in orders:
            blotter.submit_order(order)

        # ----------------------------------------------------------------------
        # Step D: Record Daily Portfolio NAV Metrics
        # 步骤 D：每日 NAV 结算归档，打印微小进度
        # ----------------------------------------------------------------------
        history_records.append({
            "date": current_date,
            "nav": nav,
            "cash": blotter.cash
        })

        if (day_idx + 1) % 100 == 0 or (day_idx + 1) == len(backtest_dates):
            _log.info("   [回测进度] 第 %3d/%d 交易日 | 今日净资产 NAV = %s USD", day_idx + 1, len(backtest_dates), f"{nav:,.2f}")

    # 3. Assemble and return performance metrics DataFrame
    # 组装并返回包含每日结算价值的时序 DataFrame
    history_df = pd.DataFrame(history_records).set_index("date")
    _log.info("事件驱动回测循环圆满完成！回测区间共涵盖 %d 个交易日。", len(history_df))
    return history_df
