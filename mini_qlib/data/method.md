# MiniQLib 核心数据与算子引擎方法手册 (`mini_qlib/data`)

本手册详细介绍了 `mini_qlib/data` 目录下的所有核心文件、类、方法及函数。本模块是整个 MiniQLib 的“计算地基”，负责抽象语法树（AST）构建、数学算子计算、高安全沙箱编译以及本地 DuckDB 行情存取。

---

## 一、 模块概述 (Module Overview)

`mini_qlib/data` 目录是多因子计算的核心驱动层，其核心设计逻辑如下：
```text
  [ 因子公式字符串 ] e.g. "Mean($close, 5) - $close"
         │
         ▼ (通过 parse_field 正则解析)
  [ Python 表达式代码 ] e.g. "Mean(Feature('close'), 5) - Feature('close')"
         │
         ▼ (通过 DataHandler.eval() 沙箱化动态编译)
  [ AST 抽象语法树对象 ] (由 MiniExpression 派生的算子节点组成)
         │
         ▼ (调用 .load(df, context) 并递归向下透传缓存)
  [ 计算输出 pd.Series ] (严格隔离跨股票时序，消除重复子树计算)
```

---

## 二、 文件结构图 (File Structure)

* `expression.py`：定义终极基类 `MiniExpression` 及原子变量加载节点 `Feature`、`PFeature`。
* `ops.py`：收集并实现所有一元数学算子（如 `Abs`）、二元算子（如 `Add`）、三元算子（如 `If`）及核心时序滚动算子（如 `Mean`、`Ref`）。
* `handler.py`：实现动态配置解析、AST 沙箱化评估与特征/标签矩阵的高性能合并计算。
* `load_data.py`：实现与本地高性能时序数据库 DuckDB 的读取、写入及增量对齐。

---

## 三、 快速参考索引表 (Quick Reference Table)

| 文件名 (File) | 类名/函数名 (Class/Function) | 方法/函数签名 (Method/Function Signature) | 作用描述 (Description) |
| :--- | :--- | :--- | :--- |
| **`expression.py`** | `MiniExpression` | `load(df, context=None) -> pd.Series` | 因子计算统一入口，内置缓存控制。 |
| | | `_load_internal(df, context=None)` | 子类必须实现的物理计算逻辑。 |
| | | `get_extended_window_size() -> (int, int)` | 计算所需向左/向右的历史与未来数据扩展长度。 |
| | `Feature` | `__init__(name: str)` | 构造基础量价特征节点（如 `$close`）。 |
| | `PFeature` | — | 构造财务时点特征节点（如 `$$revenue`）。 |
| **`ops.py`** | `ExpressionOps` | `get_longest_back_rolling() -> int` | 自动追溯子树中最长历史回溯期。 |
| | `Rolling` | `__init__(feature, N, min_periods=1)` | 滚动时间窗口算子基类（N 为窗口大小）。 |
| | `Ref` | `_load_internal(df, context=None)` | 历史引用算子，获取 $N$ 天前的数据。 |
| | `Mean`/`Sum`/`Std`/`Max`/`Min` | — | 移动平均、求和、标准差、最大/最小值滚动计算。 |
| | `parse_field` | `parse_field(field: str) -> str` | 将字符串公式正则转换为 Python 实例化代码。 |
| | `get_op_namespace` | `get_op_namespace() -> dict` | 获取 eval 所需的算子安全名字空间。 |
| **`handler.py`** | `DataHandler` | `__init__(df, config)` | 动态装配与编译特征/标签配置。 |
| | | `setup(context=None) -> pd.DataFrame` | 统一调度计算，返回行对齐的因子大矩阵。 |
| **`load_data.py`**| `init_prices_table`| `init_prices_table(con)` | 安全初始化 DuckDB `prices` 表。 |
| | `insert_prices` | `insert_prices(con, df) -> int` | 增量写入价格数据，主键冲突时自动替换。 |
| | `read_prices` | `read_prices() -> pd.DataFrame` | 读取全部价格数据（带未建表避坑提示）。 |

---

## 四、 核心 API 教学与示例 (Detailed API & Examples)

### 1. `expression.py` — AST 终极基类

#### 🔴 `MiniExpression` 类
所有计算算子的终极基类。重载了所有 Python 数学与比较运算符，使得初学者能够直接书写物理公式。

* **`load(df: pd.DataFrame, context: dict = None) -> pd.Series`**
  * **英文**: Evaluates the expression recursively. Uses the unique string representation (`str(self)`) as the cache key to avoid duplicate computations.
  * **中文**: 递归计算表达式的值。以公式唯一字符串（`str(self)`）作为缓存键，在 `context` 中拦截，彻底消除相同子算子的重复计算开销。
  * **参数**:
    - `df`: 带有 `['date', 'ticker']` 双重 MultiIndex 的行情数据框。
    - `context`: 共享计算缓存字典。
  * **返回值**: 计算完成的 `pd.Series`（其索引与 `df` 严格对齐）。

* **`get_extended_window_size() -> Tuple[int, int]`**
  * **英文**: Computes the required historical and future window expansion sizes (left and right offsets) to compute this factor for a specific date segment.
  * **中文**: 计算为了在特定日期区间内计算该因子，基础特征所需向左（过去）和向右（未来）扩展的观测天数。

#### 🔴 `Feature` 类
表示数据库中直接存在的列（叶子节点）。

* **`__init__(name: str)`**
  * **用法**: `Feature("close")` 对应公式中的 `$close`。

---

### 2. `ops.py` — 算子动力集

本文件定义了所有具体的计算算子。

#### 🔴 `Rolling` 类
滚动时间窗口算子的基类。**核心设计：子类（如 Mean）只需在类级别声明 `_func = "mean"`，即可通过反射自动完成底层 Pandas 滚动绑定，无需硬编码传参。**

* **`__init__(feature: MiniExpression, N: int, min_periods: int = 1)`**
  * **中文参数**:
    - `feature`: 子表达式。
    - `N`: 滚动窗口天数（必须为正整数）。
    - `min_periods`: 窗口计算所需的最小有效观测数。若前几期非 NaN 数量小于该值，则输出 `NaN`。
  * **公式序列化**:
    - 若 `min_periods = 1`（默认），`str(Mean(Feature("close"), 5))` 序列化为 `"Mean($close,5)"`。
    - 若 `min_periods = 5`，则序列化为 `"Mean($close,5,5)"`，以此精准区分不同有效窗口的缓存键。

* **`_load_internal(df: pd.DataFrame, context: dict = None) -> pd.Series`**
  * **时序隔离细节**:
    在计算滚动窗口时，底层自动检测 MultiIndex。如果存在 `ticker`，会在单股维度执行 `groupby('ticker').rolling(self.N)` 计算，**彻底避免前一只股票的历史数据污染后一只股票，从物理上杜绝 Look-ahead Bias。**

#### 🔴 常用滚动算子列表
* **`Ref(feature, N)`**: 获取 $N$ 期前的历史值。`Ref(Feature("close"), 1)` 代表昨日收盘价。
* **`Mean(feature, N, min_periods=1)`**: $N$ 日移动平均线。
* **`Sum(feature, N)`**: $N$ 日滚动求和。
* **`Std(feature, N)`**: $N$ 日滚动标准差。
* **`Max(feature, N)`**: $N$ 日最高值。
* **`Min(feature, N)`**: $N$ 日最低值。

#### 🔴 常用一元与二元算子
* 一元算子: `Abs(feature)` (绝对值), `Log(feature)` (自然对数), `Sign(feature)` (符号函数)。
* 二元算子: `Add` (`+`), `Sub` (`-`), `Mul` (`*`), `Div` (`/`), `Gt` (`>`), `Lt` (`<`), `Greater(f1, f2)` (求元素最大值), `Less(f1, f2)` (求元素最小值)。
* 三元算子: `If(condition, left, right)` (当条件满足时返回 left，否则返回 right)。

#### 🔴 `parse_field` 函数
* **`parse_field(field: str) -> str`**
  * **中文说明**: 因子公式编译器。使用正则表达式，将初学者书写的简洁公式字串转换成等价的可执行 Python 代码。
  * **示例**: `"Ref($close, 1) > $open"` ➡️ `'Ref(Feature("close"), 1) > Feature("open")'`

---

### 3. `handler.py` — 配置驱动编译器

#### 🔴 `DataHandler` 类
可插拔特征与标签的装配中心。

* **`__init__(df: pd.DataFrame, config: dict)`**
  * **中文说明**: 初始化时自动进行 AST 语法树的动态编译。配置中既支持直接传 AST 对象，也支持调用 `feature_registry`/`label_registry` 的键名，还支持书写自定义公式字符串。
  * **沙箱加固**:
    在编译自定义公式文本时，`eval` 内部显式禁用了 `__builtins__`（`{"__builtins__": {}}`），**锁死了全局危险系统函数的调用权限，构筑了极佳的因子计算安全沙箱。**

* **`setup(context: dict = None) -> pd.DataFrame`**
  * **中文说明**: 统一调度所有特征与标签的计算，并在行维度执行高性能对齐合并。
  * **返回值**: 合并后的 DataFrame，包含所有因子列及 `label` 列。

---

### 4. `load_data.py` — DuckDB 数据网关

* **`read_prices() -> pd.DataFrame`**
  * **中文说明**: 从 DuckDB 数据库读取全部已下载的价格行情数据。
  * **避坑引导**: 内置对 Windows 独占锁和空数据库的友好捕获提示，当检测到数据库尚未进行初始化时，会自动打印出增量抓取指令：`uv run python mini_qlib/scripts/fetch_data.py`。

* **`insert_prices(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int`**
  * **中文说明**: 将行情数据框增量写入数据库。采用 `INSERT OR REPLACE` 语法，当遭遇 `(date, ticker)` 主键冲突时自动覆盖更新，确保数据的安全与纯净。

---

## 五、 初学者极速开始示例 (Quick-Start for Beginners)

以下是一个完整的独立可运行脚本，展示了如何使用 `mini_qlib/data` 下的类和方法自行构建和计算因子：

```python
import pandas as pd
import numpy as np
from mini_qlib.data.expression import Feature
from mini_qlib.data.ops import Mean, Ref, parse_field, get_op_namespace
from mini_qlib.data.handler import DataHandler

# 1. 构造一个包含 2 只股票、3 个交易日的模拟 MultiIndex 面板数据
records = [
    {"date": "2026-05-01", "ticker": "AAPL", "open": 100.0, "close": 102.0, "volume": 1000},
    {"date": "2026-05-01", "ticker": "MSFT", "open": 200.0, "close": 198.0, "volume": 500},
    {"date": "2026-05-02", "ticker": "AAPL", "open": 102.0, "close": 105.0, "volume": 1200},
    {"date": "2026-05-02", "ticker": "MSFT", "open": 198.0, "close": 202.0, "volume": 600},
    {"date": "2026-05-03", "ticker": "AAPL", "open": 105.0, "close": 103.0, "volume": 800},
    {"date": "2026-05-03", "ticker": "MSFT", "open": 202.0, "close": 201.0, "volume": 400},
]
df = pd.DataFrame(records)
df["date"] = pd.to_datetime(df["date"])
df = df.set_index(["date", "ticker"]).sort_index()

# 2. 方法 A: 使用 Python 运算符重载原生拼接 AST 计算树
close_f = Feature("close")
open_f = Feature("open")
my_factor_ast = (close_f - open_f) / open_f  # K线实体比例

# 调用计算，启用局部缓存
context = {}
res_ast = my_factor_ast.load(df, context=context)
print("🚀 原生 AST 算子计算结果:")
print(res_ast)

# 3. 方法 B: 书写自定义公式，使用 DataHandler 进行沙箱一键合并编译
pipeline_config = {
    "features": {
        "MY_KMID": "($close - $open) / $open",              # 动态编译自定义公式
        "MA_BIAS": "Mean($close, 2) / $close - 1",          # 2日滚动均线偏离度
    },
    "labels": {
        "label_1d": "Ref($close, -1) / $close - 1"           # 未来1日收益率
    }
}

handler = DataHandler(df, pipeline_config)
result_matrix = handler.setup()

print("\n🚀 DataHandler 自动装配并计算的因子矩阵:")
print(result_matrix)
```
