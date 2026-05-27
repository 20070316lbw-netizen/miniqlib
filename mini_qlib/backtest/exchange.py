# -*- coding: utf-8 -*-
"""
Exchange: Simulating the Day-Frequency Market Execution Engine
Exchange: 模拟日频交易市场的成交撮合引擎

Executes pending orders on next available open price with slippage and commission penalties.
Enforces liquidity limits (partial fill + immediate cancel) and guards against causality violations.
在下一个可交易日的开盘价上执行挂单，并扣除滑点和佣金损耗。
执行流动性容量限制（部分成交，超额立即自动撤销），并防止时间因果律泄露。
"""
import pandas as pd
from .blotter import Blotter, Order
from mini_qlib.utils.log import get_logger

_log = get_logger(__name__)


class Exchange:
    """
    Simulates a physical stock exchange to match pending buy/sell orders.
    模拟物理证券交易所，撮合挂起的买卖订单。
    """

    @staticmethod
    def match_orders(
        blotter: Blotter,
        current_date: pd.Timestamp,
        data_portal,
        max_volume_ratio: float = 0.1,
        slippage: float = 0.0005,
        fee_rate: float = 0.0003,
        tax_rate: float = 0.001,
    ):
        """
        Match pending orders using the Next-Open price of the current transaction day.
        使用当前交易日的"次日开盘价（Next-Open Price）"撮合挂起的挂单。

        Parameters / 参数:
            blotter (Blotter): The portfolio ledger/ 账户分类账簿。
            current_date (pd.Timestamp): The current execution day in backtest loop / 当前成交撮合模拟交易日。
            data_portal (DataPortal): The sandboxed historical data source / 行情隔离沙箱网关。
            max_volume_ratio (float): Maximum market share of a stock's volume executable per day.
                                      仅对买入订单生效，卖出上限由实际持仓量控制。
                                      Applied to BUY orders only; SELL caps are controlled by actual holdings.
            slippage (float): Percentage penalty representing bid-ask spread friction / 滑点惩罚率。
            fee_rate (float): Standard transaction commission / 券商经手费与佣金率。
            tax_rate (float): Stamp duty tax applied only to SELL transactions / 单边印花税率（仅卖出收取）。
        """
        # IMPORTANT: 必须对 open_orders 做浅拷贝再遍历，因为循环内会动态修改 blotter.open_orders
        # （execute_fill 和 cancel_order 会从中移除元素），直接在原列表上迭代会导致跳过元素。
        # IMPORTANT: Must shallow-copy open_orders before iterating because execute_fill and
        # cancel_order modify blotter.open_orders in-place (removing elements).
        pending_list = list(blotter.open_orders)

        for order in pending_list:
            # 1. Enforce strict T+1 latency: Orders submitted at T can ONLY be executed at >= T + 1 day
            # 强行约束 T+1 成交延迟：T 日决策提交的订单，最早只能在 T + 1 周期及以后执行，彻底封死零秒偷看成交价的未来函数
            if order.timestamp >= current_date:
                continue

            # Ensure causality holding in physical timestamp domain
            # 物理时间层面上，强制因果律断言校验：成交撮合时间必须严格滞后于订单提交时间
            assert current_date >= order.timestamp + pd.Timedelta(days=1), (
                f"Causality Violation! Order submitted on {order.timestamp.strftime('%Y-%m-%d')} "
                f"cannot be filled on same or prior date {current_date.strftime('%Y-%m-%d')}."
            )

            ticker = order.ticker

            # 2. Extract next-period available market price and volume
            # 提取成交当期的开盘价（T+1 Open）以及当日总成交量
            open_price = data_portal.get_current(ticker, "open", current_date)
            market_volume = data_portal.get_current(ticker, "volume", current_date)

            # Skip matching if the stock is suspended or missing price data on this day
            # 如果该股当天停牌或价格数据缺失，跳过本次撮合，订单状态继续保持 PENDING，留待后续有交易的 Bar 撮合
            if pd.isna(open_price) or pd.isna(market_volume) or market_volume <= 0.0:
                continue

            # 3. Calculate Liquidity Capacity Limit (Max fillable volume per day)
            # 计算单日最大可成交容量上限（仅对买入应用流动性限制，卖出上限由持仓量控制）
            # Liquidity limit applies to BUY only; SELL cap is controlled by existing holdings.
            if order.direction == "BUY":
                max_fillable_volume = market_volume * max_volume_ratio
                fill_volume = min(order.volume, max_fillable_volume)
            else:
                # For SELL orders, the fillable volume is capped by the actual holding
                # that will be checked implicitly via blotter positions;
                # here we just cap against the order volume itself.
                fill_volume = order.volume

            if fill_volume <= 0.0:
                continue

            # 4. Apply slippage friction representing immediate execution impact
            # 施加百分比滑点磨损（买入价格上浮，卖出价格下折）
            if order.direction == "BUY":
                fill_price = open_price * (1.0 + slippage)
            else:
                fill_price = open_price * (1.0 - slippage)

            # Optional execution-time rebalance check:
            # If strategy supplies a target cash budget (estimated on T close),
            # cap next-open fill volume to prevent systematic over-allocation on gap-up opens.
            if order.direction == "BUY" and getattr(order, "target_cash", None) is not None and fill_price > 0.0:
                target_cash = max(0.0, float(order.target_cash))
                fill_volume = min(fill_volume, target_cash / fill_price)

            # 5. Apply standard transactional expenses
            # 计算交易所摩擦损耗成本
            fill_amount = fill_volume * fill_price
            commission = fill_amount * fee_rate
            if order.direction == "SELL":
                # Sell transactions face single-side stamp duty tax (e.g. 0.1% Chinese Stamp Tax)
                # 卖出端扣减额外印花税（如中国 A 股千分之一印花税）
                commission += fill_amount * tax_rate

            # 6. Protect against Cash Overdraft (BUY Order Cash Protection)
            # 可用现金兜底防超额透支拦截（针对买入订单）：
            if order.direction == "BUY":
                required_total_cash = fill_amount + commission
                if blotter.cash < required_total_cash:
                    # If cash is insufficient to buy even 1 single share, cancel the order completely
                    # 如果余额完全不够买入 1 股，将订单标记为 CANCELLED 移出队列，保障逻辑健壮
                    estimated_volume = blotter.cash / (fill_price * (1.0 + fee_rate))
                    if estimated_volume < 1.0:
                        _log.warning("现金不足购买1股，订单强制撤销: ORD_ID=%s, Ticker=%s, AvailableCash=%.2f", order.order_id, ticker, blotter.cash)
                        blotter.cancel_order(order.order_id, current_date)
                        continue
                    else:
                        # Auto-scale down the BUY volume to match the maximum available cash limit
                        # 降额撮合：将股数缩减至当前最大可用现金的极限，保护资金底线
                        old_vol = fill_volume
                        fill_volume = float(int(estimated_volume))
                        _log.warning("可用现金不足，买入股数自动缩容降额: ORD_ID=%s, Ticker=%s, %d股 -> %d股", order.order_id, ticker, old_vol, fill_volume)
                        fill_amount = fill_volume * fill_price
                        commission = fill_amount * fee_rate

            # 7. Complete physical ledger update in Blotter
            # 记录真正的成交结账并移出挂单队列，超额的股数相当于在物理上被即刻取消，实现最干净且健壮的极简逻辑
            blotter.execute_fill(order.order_id, fill_volume, fill_price, commission, current_date)
            _log.info("订单撮合成功: ORD_ID=%s, Ticker=%s, 方向=%s, 股数=%d, 价格=%.2f, 费用=%.2f", 
                      order.order_id, ticker, order.direction, fill_volume, fill_price, commission)
