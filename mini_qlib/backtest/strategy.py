# -*- coding: utf-8 -*-
"""
Strategy Framework for MiniQLib Backtesting Engine.
Defines the base class and concrete strategy implementations.
"""
from typing import List, Optional
import pandas as pd

from .blotter import Order, Blotter
from .data_portal import DataPortal


class BaseStrategy:
    """
    Base Strategy class.
    All custom quantitative strategies in MiniQLib should inherit from this class.
    """
    def __init__(self):
        pass

    def on_bar(
        self,
        current_date: pd.Timestamp,
        data_portal: DataPortal,
        blotter: Blotter,
        nav: float,
        predictions: Optional[pd.Series] = None
    ) -> List[Order]:
        """
        Callback triggered on every trading bar (day).
        Generates and returns a list of Order objects.

        Parameters:
            current_date (pd.Timestamp): The current trading day.
            data_portal (DataPortal): High-fidelity read-only market data gateway.
            blotter (Blotter): Account ledger containing cash, positions, and order history.
            nav (float): Account net asset value calculated at the close of today.
            predictions (pd.Series, optional): ML factor prediction scores mapping to (date, ticker).

        Returns:
            List[Order]: List of generated trade orders to be submitted to the blotter.
        """
        return []


class TopKRotationStrategy(BaseStrategy):
    """
    Classic Top-K Equal Weight Stock Rotation Strategy.
    Ported from original hardcoded loop in backtest.py.
    """
    def __init__(self, K: int = 5):
        super().__init__()
        self.K = K
        self.order_id_counter = 0

    def on_bar(
        self,
        current_date: pd.Timestamp,
        data_portal: DataPortal,
        blotter: Blotter,
        nav: float,
        predictions: Optional[pd.Series] = None
    ) -> List[Order]:
        orders = []
        if predictions is None or predictions.empty:
            return orders

        try:
            daily_preds = predictions.loc[current_date].dropna()
        except KeyError:
            # Skip decision-making if no predictions available for today
            daily_preds = pd.Series(dtype="float64")

        if daily_preds.empty:
            return orders

        # Sort scores descending and pick the Top-K tickers
        sorted_tickers = daily_preds.sort_values(ascending=False)
        top_k_tickers = list(sorted_tickers.head(self.K).index)

        # Target capital allocation per stock (Equal weight)
        target_value_per_stock = nav / self.K

        # Action 1: Liquidation (SELL orders for tickers dropping out of Top-K)
        for held_ticker in list(blotter.positions.keys()):
            if held_ticker not in top_k_tickers:
                shares_to_sell = blotter.positions[held_ticker].volume
                if shares_to_sell > 0.0:
                    self.order_id_counter += 1
                    orders.append(Order(
                        order_id=f"ORD_{self.order_id_counter:06d}",
                        ticker=held_ticker,
                        direction="SELL",
                        volume=shares_to_sell,
                        timestamp=current_date,
                    ))

        # Action 2: Rebalancing / Allocation (BUY orders for Top-K tickers)
        for target_ticker in top_k_tickers:
            close_price = data_portal.get_current(target_ticker, "close", current_date)
            if not pd.isna(close_price) and close_price > 0.0:
                # Calculate target shares count based on target allocation value
                target_volume = target_value_per_stock / close_price
                current_volume = (
                    blotter.positions[target_ticker].volume
                    if target_ticker in blotter.positions
                    else 0.0
                )

                # Generate BUY order if there is an under-allocated share gap
                volume_to_buy = target_volume - current_volume
                if volume_to_buy > 0.0:
                    target_cash_gap = max(0.0, (target_volume - current_volume) * close_price)
                    self.order_id_counter += 1
                    orders.append(Order(
                        order_id=f"ORD_{self.order_id_counter:06d}",
                        ticker=target_ticker,
                        direction="BUY",
                        volume=volume_to_buy,
                        timestamp=current_date,
                        target_cash=target_cash_gap,
                    ))

        return orders


class AppleDCAStrategy(BaseStrategy):
    """
    Dollar Cost Averaging (DCA) Strategy for a target stock (default: AAPL).
    On each trading day, submits a buy order for either a fixed share count or a fixed cash amount.
    """
    def __init__(self, ticker: str = "AAPL", dca_amount: float = 10.0, is_shares: bool = True):
        super().__init__()
        self.ticker = ticker
        self.dca_amount = dca_amount
        self.is_shares = is_shares
        self.order_id_counter = 0

    def on_bar(
        self,
        current_date: pd.Timestamp,
        data_portal: DataPortal,
        blotter: Blotter,
        nav: float,
        predictions: Optional[pd.Series] = None
    ) -> List[Order]:
        orders = []
        
        # ── 现金耗尽提前返回 ──────────────────────────────────────────
        # 当账户现金归零时，后续所有定投订单都会被交易所取消，产生无意义的
        # 计算开销和日志噪音。此处直接短路，节省约 80%+ 的无效交易日循环。
        if blotter.cash <= 0.0:
            return orders

        # Get today's close price to calculate the order details
        close_price = data_portal.get_current(self.ticker, "close", current_date)
        if pd.isna(close_price) or close_price <= 0.0:
            return orders

        if self.is_shares:
            # DCA by buying fixed number of shares.
            # target_cash 用作交易所撮合时的预算帽：如果 T+1 开盘价高于 T 日收盘价，
            # Exchange 会将成交量缩至 target_cash / fill_price 以内，防止跳涨超支。
            # 这意味着"每次买 N 股"在跳涨日实际可能买不到 N 股，属刻意保护机制。
            volume = self.dca_amount
            target_cash = volume * close_price
        else:
            # DCA by investing fixed cash amount (e.g. buy $1000 USD of Apple)
            volume = self.dca_amount / close_price
            target_cash = self.dca_amount

        # Submit a buy order to the exchange for processing on T+1
        self.order_id_counter += 1
        orders.append(Order(
            order_id=f"ORD_DCA_{self.order_id_counter:06d}",
            ticker=self.ticker,
            direction="BUY",
            volume=volume,
            timestamp=current_date,
            target_cash=target_cash
        ))
        
        return orders
