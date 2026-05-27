# MiniQLib 事件驱动回测引擎方法手册 (`mini_qlib/backtest`)

本手册详细介绍了 `mini_qlib/backtest` 目录下的所有核心文件、类、方法及函数。本模块是 MiniQLib 的“交易仿真与账簿结账系统”，采用极度严苛的 Bar-by-Bar 事件驱动控制，确保回测高保真度，物理粉碎未来函数。

---

## 一、 模块概述 (Module Overview)

`mini_qlib/backtest` 目录提供了全套仿真的物理交易所、交易账簿和行情网关：
```text
                  [ 策略信号决策 (T日 Close) ]
                              │
                              ▼ (提交至订单簿)
                  [ 待成交队列 Order (PENDING) ]
                              │
        ┌─────────────────────┴─────────────────────┐ (T+1日开盘推进)
        ▼ (物理成交延迟)                            ▼ (容量与流动性限制)
   严格 T+1 成交延迟                           大额订单仅成交前10%成交量
  使用 T+1日 Open 撮合                        未成交的股数即刻自动撤销
        │                                           │
        └─────────────────────┬─────────────────────┘
                              ▼
                 [ 交易所撮合 Exchange.match() ]
                              │
                              ▼ (结账并扣减印花税、滑点与佣金)
                   [ 持仓与现金账簿 Blotter ] ➡️ 结算每日 NAV
```

---

## 二、 文件结构图 (File Structure)

* `data_portal.py`：高性能只读行情网关，二分法物理切片，向策略层绝对遮蔽未来价格。
* `blotter.py`：投资组合账户系统，管理现金变动、股票持仓加权平均买入成本及挂单历史。
* `exchange.py`：物理撮合交易所，模拟摩擦力（滑点、印花税、手续费）与流动性部分成交退回。
* `backtest.py`：事件驱动回测总控制器，调度每日 Bar 推进、交易所撮合和 Top-K 轮动策略。

---

## 三、 快速参考索引表 (Quick Reference Table)

| 文件名 (File) | 类名/函数名 (Class/Function) | 方法/函数签名 (Method/Function Signature) | 作用描述 (Description) |
| :--- | :--- | :--- | :--- |
| **`data_portal.py`** | `DataPortal` | `__init__(df: pd.DataFrame)` | 初始化行情网关，物理对齐并预排序。 |
| | | `get_history(ticker, field, current_date, N) -> pd.Series` | 安全获取指定股票截至今日的 $N$ 期历史。 |
| | | `get_current(ticker, field, current_date) -> float` | 获取指定股票在今日的瞬时行情（开盘/收盘价）。 |
| **`blotter.py`** | `Order` | `__init__(order_id, ticker, direction, volume, timestamp)` | 构造交易订单，初始状态一律为 `PENDING`。 |
| | `Position` | `update(fill_volume, fill_price, direction)` | 更新持仓数量，买入时自动计算加权平均成本。 |
| | `Blotter` | `submit_order(order)` | 向待撮合队列提交新订单。 |
| | | `execute_fill(order_id, fill_volume, fill_price, commission, timestamp)` | 执行成交划转，扣减现金、增加持仓并写入日志。 |
| | | `get_nav(current_prices: dict) -> float` | 计算实时资产净值（现金 + 股票市值）。 |
| **`exchange.py`** | `Exchange` | `match_orders(blotter, current_date, data_portal, ...)` | 交易所撮合核心逻辑，包含滑点、税费、延迟及防透支。 |
| **`backtest.py`** | `run_backtest` | `run_backtest(df, predictions, initial_cash=1e6, K=5, ...)` | 回测大循环控制器，跑通 Top-K 等权股票轮动策略。 |

---

## 四、 核心 API 教学与示例 (Detailed API & Examples)

### 1. `data_portal.py` — 高性能行情隔离沙箱

#### 🔴 `DataPortal` 类
只读的数据网关，是防未来函数的头号功臣。

* **`get_history(ticker: str, field: str, current_date: pd.Timestamp, N: int) -> pd.Series`**
  * **英文**: Retrieves a historical data series of length N for a ticker up to the `current_date`. Future prices are physically isolated using sorted MultiIndex binary search.
  * **中文**: 获取指定股票截至 `current_date` 的最新 $N$ 期历史时序。利用已按 `['date', 'ticker']` 预排序索引的 `loc[:current_date]` 切片，在 $O(\log N)$ 内直接拦截未来数据。
  * **示例**: 在 `2026-05-02`，策略通过该接口绝对查不到 `2026-05-03` 的数据，直接杜绝了时空越权。

---

### 2. `blotter.py` — 仿真账户分类账簿

#### 🔴 `Position` 类
管理个股的持仓量与成本价格。

* **`update(fill_volume: float, fill_price: float, direction: str)`**
  * **中文**: 更新持仓股数与成本价。
  * **原理**: 买入（`BUY`）时，采用加权平均公式更新：
    $$\text{cost\_price} = \frac{\text{volume} \times \text{cost\_price} + \text{fill\_volume} \times \text{fill\_price}}{\text{volume} + \text{fill\_volume}}$$
    卖出（`SELL`）时，直接扣减数量，若股数归零，则清除个股持仓成本，成本核算极为纯净。

#### 🔴 `Blotter` 类
管理账户资金、所有持仓表及历史成交订单簿。

* **`execute_fill(...)`**
  * **中文**: 完成订单的最终物理成交划转。
  * **流程**:
    1. 将成交订单移出 `open_orders` 待撮合挂单队列，更新其状态为 `FILLED`。
    2. 计算交易额，扣除券商佣金及卖出印花税（买入：`cash -= (fill_amount + commission)`；卖出：`cash += (fill_amount - commission)`）。
    3. 调用对应 `Position.update()`，更新股票持仓。
    4. 产生一笔成交明细归档到 `trade_history` 中。

---

### 3. `exchange.py` — 仿真交易所撮合器

#### 🔴 `Exchange` 类
实现日频交易市场的撮合成交逻辑。

* **`match_orders(...)`**
  * **中文说明**: 交易所对挂单簿中的所有 `PENDING` 订单进行撮合。
  * **核心拦截逻辑**:
    1. **时空因果律断言**: 成交撮合日必须比下单日期**严格滞后至少 1 天** (`current_date >= order.timestamp + 1`)。
    2. **物理价格撮合**: 强制使用撮合当日（$T+1$）的开盘价 `open` 价格进行撮合。
    3. **流动性容量保护**: 每日成交量不得超过市场真实日成交量的 `max_volume_ratio`（默认 10%）。多出股数**即刻自动撤单**，不在挂单簿滞留。
    4. **摩擦成本**: 买入加收滑点，卖出扣除滑点（`slippage`），并针对卖出端单边加收印花税（`tax_rate`）。
    5. **现金超额透支拦截 (Overdraft Protection)**:
       * 若可用现金少于 1 股本息，直接将订单置为 `CANCELLED` 并移出挂单队列，防止负现金发生。
       * 若可用资金足够买入部分股票，交易所会自动执行**缩量降额撮合**（买入最大允许股数），筑牢资金安全底线。

---

### 4. `backtest.py` — 总事件循环

* **`run_backtest(...)`**
  * **中文说明**: 一键拉起高保真事件驱动回测大循环。
  * **回测主流程**:
    ```python
    for current_date in backtest_dates:
        # 1. 交易所撮合上一个交易日遗留的挂单
        Exchange.match_orders(...)
        # 2. 盘点当前持仓的最新收盘折合市值，计算今日净资产 NAV
        nav = blotter.get_nav(...)
        # 3. 策略决策：获取预测得分最高的前 K 只股票
        #    - 清仓：对于掉出 Top-K 的持仓股，在 T 日提交足额 SELL 挂单
        #    - 补仓/建仓：对于在 Top-K 内的股票，测算目标股数并提交 BUY 挂单
    ```

---

## 五 & 六、 初学者极速开始示例 (Quick-Start for Beginners)

以下是完整可直接运行的独立测试脚本，模拟了初学者从“创建行情 ➡️ 下单 ➡️ 推进时间轴 ➡️ 交易所撮合 ➡️ 盘点持仓 NAV”的完整仿真量化交易回路：

```python
import pandas as pd
from mini_qlib.backtest.data_portal import DataPortal
from mini_qlib.backtest.blotter import Order, Blotter
from mini_qlib.backtest.exchange import Exchange

# 1. 创建高仿真行情数据框 (AAPL 在 T+1 日开盘跳空上涨，且交易活跃)
records = [
    {"date": "2026-05-01", "ticker": "AAPL", "open": 100.0, "close": 102.0, "volume": 1000},
    {"date": "2026-05-02", "ticker": "AAPL", "open": 105.0, "close": 108.0, "volume": 2000},
]
df = pd.DataFrame(records)
df["date"] = pd.to_datetime(df["date"])
df = df.set_index(["date", "ticker"]).sort_index()

# 2. 初始化沙箱网关与 10,000 USD 的交易账簿
portal = DataPortal(df)
blotter = Blotter(initial_cash=10000.0)

t1 = pd.Timestamp("2026-05-01")
t2 = pd.Timestamp("2026-05-02")

print(f"🎬 初始状态: 现金 = {blotter.cash:,.2f} USD")

# 3. 策略在 T1 时刻下达买单：买入 50 股 AAPL (由于 T+1 延迟，此时以 PENDING 挂起)
order = Order(
    order_id="ORD_001",
    ticker="AAPL",
    direction="BUY",
    volume=50.0,
    timestamp=t1
)
blotter.submit_order(order)
print(f"📌 提交挂单: {order}")

# 4. 在 T1 日推进撮合 -> 验证 T+1 时空隔离，订单不予成交
Exchange.match_orders(blotter, current_date=t1, data_portal=portal)
print(f"⏳ T1 日撮合后挂单状态: {order.status} (应为 PENDING)")

# 5. 时间轴正式推进至 T2 日，执行 T+1 撮合
# 模拟 1% 的严重滑点与千分之三手续费
Exchange.match_orders(
    blotter=blotter,
    current_date=t2,
    data_portal=portal,
    max_volume_ratio=0.1,    # 当日最大可买入量：2000 * 10% = 200 股
    slippage=0.01,           # 1% 滑点 -> 成交价 = 105 * (1 + 1%) = 106.05
    fee_rate=0.003,          # 0.3% 手续费
    tax_rate=0.0
)

print(f"\n🎉 T2 日撮合后订单状态: {order.status} (应为 FILLED)")
trade = blotter.trade_history[0]
print(f"📊 实际撮合成交价: {trade['price']:.2f} USD (含滑点，开盘价为 105.00)")
print(f"📊 交易所扣减手续费: {trade['commission']:.2f} USD")

# 6. 盘点账户持仓与今日收盘资产净值 NAV
# AAPL T2 收盘价为 108.00
nav_prices = {"AAPL": 108.00}
pos_val = blotter.get_positions_value(nav_prices)
total_nav = blotter.get_nav(nav_prices)

print(f"\n📈 结账信息:")
print(f"   剩余现金 (Cash): {blotter.cash:,.2f} USD")
print(f"   股票持仓市值 (Holdings Value): {pos_val:,.2f} USD")
print(f"   账户总资产净值 (NAV): {total_nav:,.2f} USD")
```
