# Database Directory / 数据库管理模块

## 📌 Introduction / 简介
本目录是 `mini_qlib` 的核心数据存储中心，采用高性能的 **DuckDB** 列式数据库引擎进行数据管理。
这里存放了标普 500（S&P 500）成分股的十年历史日频行情数据，以及完整的 SEC EDGAR 财务报表数据。

---

## 💾 Core Databases / 核心数据库文件
1. **`edgar.duckdb`**（主要基本面数据）：内含 25.8 万条标普 500 公司历史财务报告明细（包括利润表、资产负债表、现金流量表）。
2. **`sp500.duckdb`**（主要行情价格数据）：（调用 `get_db()` 时自动按需创建）包含 `prices` 行情表，存放日频基础量价数据。

---

## 📊 Database Schema / 数据结构与表定义

### 1. 行情价格表 `prices` (位于行情库)
* **用途**：日频 OHLCV 量价行情。
* **结构定义**：
  | 列名 (Column) | 类型 (Type) | 键/约束 (Constraint) | 描述 (Description) |
  | :--- | :--- | :--- | :--- |
  | `date` | DATE | PRIMARY KEY | 交易日期 |
  | `ticker` | VARCHAR | PRIMARY KEY | 股票代码 (例如 AAPL) |
  | `open` | DOUBLE | | 开盘价 |
  | `high` | DOUBLE | | 最高价 |
  | `low` | DOUBLE | | 最低价 |
  | `close` | DOUBLE | | 收盘价 |
  | `volume` | BIGINT | | 交易量 |

### 2. 利润表 `income` (位于 edgar 库)
* **用途**：季度/年度利润表主营指标。
* **结构定义**：
  | 列名 | 类型 | 描述 |
  | :--- | :--- | :--- |
  | `ticker` | VARCHAR | 股票代码 |
  | `period_end` | DATE | 财报期末日期 (Accounting Period End) |
  | `filed` | DATE | 真实报送日期 (SEC Filed Date) —— **PIT 核心列** |
  | `form` | VARCHAR | 报表类型 (`10-K` / `10-Q` / `10-K/A` / `10-Q/A`) |
  | `revenue` | DOUBLE | 营业收入 (Revenue) |
  | `gross_profit`| DOUBLE | 毛利润 (Gross Profit) |
  | `op_income` | DOUBLE | 营业利润 (Operating Income) |
  | `net_income` | DOUBLE | 净利润 (Net Income) |
  | `eps_diluted` | DOUBLE | 稀释后每股收益 (EPS Diluted) |

### 3. 资产负债表 `balance` (位于 edgar 库)
* **用途**：资产、负债、权益与负债情况。
* **结构定义**：
  | 列名 | 类型 | 描述 |
  | :--- | :--- | :--- |
  | `ticker` | VARCHAR | 股票代码 |
  | `period_end` | DATE | 财报期末日期 |
  | `filed` | DATE | 真实报送日期 —— **PIT 核心列** |
  | `form` | VARCHAR | 报表类型 (`10-K` / `10-Q` 等) |
  | `total_assets`| DOUBLE | 总资产 (Total Assets) |
  | `total_liabilities`| DOUBLE | 总负债 (Total Liabilities) |
  | `equity` | DOUBLE | 股东权益 (Stockholders' Equity) |
  | `cash` | DOUBLE | 现金与现金等价物 (Cash and Equivalents) |
  | `total_debt` | DOUBLE | 长期债务总额 (Long-Term Debt) |

### 4. 现金流量表 `cashflow` (位于 edgar 库)
* **用途**：经营现金流、资本开支、自由现金流等。
* **结构定义**：
  | 列名 | 类型 | 描述 |
  | :--- | :--- | :--- |
  | `ticker` | VARCHAR | 股票代码 |
  | `period_end` | DATE | 财报期末日期 |
  | `filed` | DATE | 真实报送日期 —— **PIT 核心列** |
  | `form` | VARCHAR | 报表类型 |
  | `cfo` | DOUBLE | 经营活动产生的现金流量净额 (Cash from Operations) |
  | `capex` | DOUBLE | 资本支出 (Capital Expenditure) |
  | `fcf_direct` | DOUBLE | 直接自由现金流 (Free Cash Flow) |

---

## 📈 数据特点：Point-in-Time (PIT) 机制
在经典的选股和多因子回测中，**“未来函数/前瞻偏差 (Look-Ahead Bias)”** 是导致模型实盘溃败的最大杀手。

### 🚨 什么是前瞻偏差？
假设某公司 2025 年第四季度（2025-12-31 财报期末）的净利润大幅增长。如果我们使用 `period_end`（2025-12-31）直接去参与 2026 年 1 月 5 日的选股计算，就会产生严重的前瞻偏差——**因为在 2026-01-05 那天，公司根本还没有向 SEC 提交财报，外界根本不知道该数据！该财报真实的公布时间可能延迟到 2026 年 2 月底。**

### 🛡️ PIT 数据库如何解决该问题？
我们的财务数据库采用了完美的 **Point-in-Time** 数据模型，同时保留了两个核心时间戳：
1. **`period_end` (会计期末日)**：指财报在账面上所处的季度截止日（如 `2025-12-31`）。
2. **`filed` (真实披露日)**：指该财报正式向 SEC 递交并向市场公开的日期（如 `2026-02-15`）。

**在因子引擎计算时**：
* 任何在历史交易日 $T$（例如 `2026-01-10`）进行的因子计算，**只允许检索 `filed <= T` 的财务报表**。
* 这样就能够确保回测时使用的数据与当时历史物理时间点上市场所掌握的数据完全吻合，彻底杜绝回测“画大饼”现象！
