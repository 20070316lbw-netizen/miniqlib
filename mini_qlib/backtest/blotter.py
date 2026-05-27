# -*- coding: utf-8 -*-
"""
Blotter: Quant Trading Account, Positions & Order Management System
Blotter: 量化交易账户、持仓与订单管理系统

Manages portfolio state (cash, holdings), logs executed trades, and tracks the 
lifecycle of open orders (Pending, Filled, Cancelled).
管理投资组合状态（现金、持仓）、记录执行的交易，并追踪待成交订单（挂单、成交、撤单）的生命周期。
"""
from typing import Optional, Dict, List
import pandas as pd


class Order:
    """
    Represents a trading order in the backtest engine.
    代表回测引擎中的交易订单。
    """

    def __init__(
        self,
        order_id: str,
        ticker: str,
        direction: str,
        volume: float,
        timestamp: pd.Timestamp,
        target_cash: Optional[float] = None,
    ):
        """
        Initialize an Order / 初始化订单。

        Parameters / 参数:
            order_id (str): Unique order identifier / 唯一订单 ID。
            ticker (str): Asset identifier / 资产代码。
            direction (str): 'BUY' or 'SELL' / 交易方向 'BUY' 或 'SELL'。
            volume (float): Number of shares to trade / 下单股数。
            timestamp (pd.Timestamp): Date when the order was submitted / 订单提交日。
        """
        self.order_id = order_id
        self.ticker = ticker
        self.direction = direction.upper()
        self.volume = float(volume)
        self.timestamp = timestamp
        # Optional target cash budget carried by strategy for execution-time rebalance checks
        self.target_cash = float(target_cash) if target_cash is not None else None
        self.status = "PENDING"  # Initial state is always PENDING / 初始状态一律为挂单中 PENDING

    def __repr__(self):
        return (
            f"Order(ID={self.order_id}, Ticker={self.ticker}, Direction={self.direction}, "
            f"Volume={self.volume}, Date={self.timestamp.strftime('%Y-%m-%d')}, Status={self.status})"
        )


class Position:
    """
    Represents a single asset holding in the portfolio.
    代表投资组合中的单只资产持仓状态。
    """

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.volume = 0.0
        self.cost_price = 0.0

    def update(self, fill_volume: float, fill_price: float, direction: str):
        """
        Update volume and average cost price upon order execution.
        当订单成交执行时，更新持仓数量与平均买入成本价。

        Parameters / 参数:
            fill_volume (float): Executed shares count / 成交股数。
            fill_price (float): Executed price per share / 成交单价。
            direction (str): 'BUY' or 'SELL' / 交易方向。
        """
        if direction.upper() == "BUY":
            if self.volume == 0.0:
                self.volume = fill_volume
                self.cost_price = fill_price
            else:
                # Update weighted average cost price
                # 计算更新后的加权平均持仓成本
                total_cost = (self.volume * self.cost_price) + (fill_volume * fill_price)
                self.volume += fill_volume
                self.cost_price = total_cost / self.volume if self.volume > 0 else 0.0
        elif direction.upper() == "SELL":
            # Cap deduction to zero
            # 减除股数，最低归零
            self.volume = max(0.0, self.volume - fill_volume)
            if self.volume == 0.0:
                self.cost_price = 0.0

    def __repr__(self):
        return f"Position(Ticker={self.ticker}, Volume={self.volume}, Cost={self.cost_price:.4f})"


class Blotter:
    """
    Portfolio Ledger that records cash balances, current holdings, trade logs, and order book.
    投资组合分类账簿，记录现金余额、当前持仓、历史交易日志以及挂单订单簿。
    """

    def __init__(self, initial_cash: float):
        """
        Initialize the Blotter ledger / 初始化账簿。

        Parameters / 参数:
            initial_cash (float): Initial available trading capital / 初始可用交易本金。
        """
        self.cash = float(initial_cash)
        self.positions: Dict[str, Position] = {}  # ticker -> Position / 持仓映射字典
        self.open_orders: List[Order] = []        # Queue of active PENDING orders / 处于 PENDING 状态的待成交挂单列表
        self.order_history: List[Order] = []      # Audit trail of all orders submitted / 包含所有订单的审计历史表
        self.trade_history: List[dict] = []       # Detailed transaction logs / 详细的交易成交历史细化日志
        self.realized_pnl: float = 0.0            # 累计已实现盈亏 / cumulative realized PnL

    def submit_order(self, order: Order):
        """
        Submit a new trading order to the queue / 向待撮合队列提交新交易订单。
        """
        order.status = "PENDING"
        self.open_orders.append(order)
        self.order_history.append(order)

    def execute_fill(self, order_id: str, fill_volume: float, fill_price: float, commission: float, timestamp: pd.Timestamp):
        """
        Mark a pending order as filled, update cash and position holdings, and log trade details.
        标记待成交订单为已成交，扣减/增加账户现金与股票持仓，并写入最终成交明细。

        Parameters / 参数:
            order_id (str): ID of the PENDING order / 挂单订单 ID。
            fill_volume (float): Number of shares successfully filled / 成功成交的股数。
            fill_price (float): Executed trade price / 实际成交价格。
            commission (float): Transaction fees & taxes incurred / 交易所扣减的佣金与印花税。
            timestamp (pd.Timestamp): Date of order execution / 实际撮合成交日。
        """
        # Find order in open orders
        # 寻找对应的挂单
        order = next((o for o in self.open_orders if o.order_id == order_id), None)
        if not order:
            return

        # Move out of pending queue and mark status as FILLED
        # 从挂单队列中移出，并更改其最终状态为 FILLED
        self.open_orders.remove(order)
        order.status = "FILLED"

        ticker = order.ticker

        # Update cash accounting based on transaction direction
        # 根据交易方向，结算可用资金余额（买入扣除佣金，卖出扣除佣金）
        if order.direction == "BUY":
            total_outlay = (fill_volume * fill_price) + commission
            self.cash -= total_outlay
        elif order.direction == "SELL":
            pos_before = self.positions.get(ticker)
            if pos_before is not None:
                matched_volume = min(fill_volume, pos_before.volume)
                self.realized_pnl += matched_volume * (fill_price - pos_before.cost_price) - commission
            total_receipt = (fill_volume * fill_price) - commission
            self.cash += total_receipt

        # Update stock holdings in portfolio positions
        # 更新投资组合持仓
        if ticker not in self.positions:
            self.positions[ticker] = Position(ticker)
        
        self.positions[ticker].update(fill_volume, fill_price, order.direction)

        # Remove from dictionary if position is fully cleared
        # 如果持仓股数已归零，从持仓字典中彻底清除节点以保持数据清爽
        if self.positions[ticker].volume <= 0.0:
            del self.positions[ticker]

        # Log detailed execution record
        # 记录成交明细日志
        trade_record = {
            "order_id": order.order_id,
            "ticker": ticker,
            "direction": order.direction,
            "volume": fill_volume,
            "price": fill_price,
            "commission": commission,
            "order_date": order.timestamp,
            "execution_date": timestamp,
        }
        self.trade_history.append(trade_record)

    def cancel_order(self, order_id: str, timestamp: pd.Timestamp):
        """
        Cancel a pending order and remove it from the active queue.
        撤销挂单中的挂起订单，并从活动队列移出。
        """
        order = next((o for o in self.open_orders if o.order_id == order_id), None)
        if order:
            self.open_orders.remove(order)
            order.status = "CANCELLED"

    def get_positions_value(self, current_prices: Dict[str, float]) -> float:
        """
        Calculate total market value of current holdings based on current prices.
        根据当前行情价格计算当前持仓股票的总市值。
        """
        value = 0.0
        for ticker, pos in self.positions.items():
            price = current_prices.get(ticker, 0.0)
            if pd.isna(price):
                price = pos.cost_price  # Fallback to cost if current price is missing / 缺值回退为买入成本价
            value += pos.volume * price
        return value

    def get_nav(self, current_prices: Dict[str, float]) -> float:
        """
        Calculate Portfolio Net Asset Value (NAV).
        计算账户总资产净值（NAV = 现金 + 持仓总市值）。
        """
        return self.cash + self.get_positions_value(current_prices)
