# Data & Operator Engine Module / 因子与算子计算引擎规范

## 📌 1. Module Philosophy / 模块开发哲学
本模块是 `mini_qlib` 的核心**计算图与算子引擎**。在设计与实现后续任何数据、算子或因子代码时，必须严格遵守以下三大哲学：
- **动态反射优先 (Reflection Over Hardcoding)**：严禁在具体算子类中硬编码属性绑定（例如手动写 `self.feature = feature`），必须全部依托基类 `ExpressionOps` 的元拦截器自动绑定，保持代码的高度精炼。
- **时序绝对隔离 (Strict Temporal Isolation)**：在处理多股票面板数据（Panel Data）时，时序操作（如 Rolling, Shift 等）必须严格按照股票（Ticker）分组计算，绝对禁止股票间的数据发生任何跨时序泄露或污染。
- **无重复计算 (Zero-Redundancy via Caching)**：因子计算树（AST）中重复出现的子树，必须通过 `context` 上下文进行高速全局缓存，实现零开销重用。

---

## 📂 2. Core File Directory / 核心文件职责划分
为避免循环导入（Circular Import），本模块目录下的文件职责被严格隔离：
1. **[expression.py](file:///c:/Users/liu/Desktop/miniqlib/mini_qlib/data/expression.py) (计算图地基)**:
   - 仅包含终极抽象基类 `MiniExpression` 及原子特征类 `Feature`、`PFeature`。
   - 实现全套 Python 运算符重载方法（`__add__`, `__sub__` 等）用以动态构建 AST 拓扑。
   - **绝对禁止在此文件中导入任何高阶算子类。**
2. **[ops.py](file:///c:/Users/liu/Desktop/miniqlib/mini_qlib/data/ops.py) (算子大本营)**:
   - 包含所有单目（`ElemOperator`）、双目（`PairOperator`/`NpPairOperator`）、三目（`If`）及滚动窗口（`Rolling`/`Ref`）算子的具体实现。
   - 通过 `__init_subclass__` 类钩子实现无硬编码的参数锁与动态属性装配。
3. **[load_data.py](file:///c:/Users/liu/Desktop/miniqlib/mini_qlib/data/load_data.py) (行情加载底座)**:
   - 负责对接 DuckDB 数据库并封装底层行情读取与合并写入接口。

---

## 📊 3. Data Schema & Representation Standards / 数据结构与表规范
所有在 `mini_qlib` 中流转的行情与基本面数据，必须严格遵循以下 Schema 及 Index 排版规范，不得混用：

### 3.1 行情 DataFrame (Market Price Data)
在进行因子计算时，输入和输出的行情 DataFrame/Series 必须符合：
- **索引规范 (Index Structure)**：
  - **多股票 Panel 场景**：必须使用 `pd.MultiIndex`，层级名（Index Level Names）固定为 `['date', 'ticker']`。`date` 必须为时间类型（或可转换的 `Timestamp`/`datetime64`），`ticker` 为字符串（如 `'AAPL'`）。
  - **单股票场景**：必须使用以 `date` 为名的单重索引 `pd.Index`。
- **列名与大小写 (Column Names & Case)**：
  - 行情基本面数据列名一律采用**纯小写**：`['open', 'high', 'low', 'close', 'volume']`。
  - 列数据类型一律使用标准浮点型 `DOUBLE` (Float64) 或整型 `BIGINT` (Int64)。

### 3.2 Point-in-Time 财务 DataFrame (PIT Fundamental Data)
在处理财务报表数据时，必须保留两个核心时间戳，以消除**前瞻偏差 (Look-Ahead Bias)**：
- **`period_end` (会计期末日)**：该财务季度截止日（如 `2025-12-31`）。
- **`filed` (真实披露日 / PIT 核心)**：该财报向 SEC 递交并向市场公开的日期（如 `2026-02-15`）。
- **回测检索规则**：在任何交易日 $T$ 进行因子计算，仅允许检索 `filed <= T` 的最新财务数据。

---

## 🛠️ 4. Operator Development Standards / 算子开发与代码编写标准
新开发或修改算子时，必须严格遵守以下代码编写标准，保持全局格式高度统一：

### 4.1 命名规范 (Naming Conventions)
- **类名 (Class Names)**：必须使用大驼峰式（PascalCase）。例如：`Abs`, `Sign`, `Rolling`, `Mean`, `Ref`。
- **参数名 (Argument Names)**：
  - 单目/滚动算子的输入特征变量统一命名为 `feature`。
  - 双目算子的左右特征输入分别统一命名为 `feature_left` 和 `feature_right`。
  - 滚动/时间序列算子的时间窗口长度参数统一命名为大写 `N`。
  - 严禁缩写或随意更改参数名（如用 `feat`、`win` 等），以防反射引擎属性绑定失败。

### 4.2 反射与初始化原则 (Metaclass & Init Rules)
- **严禁手动绑定参数**：具体子算子在定义 `__init__` 时，除非有特殊参数校验需求，否则其主体中**不写任何多余代码**，仅使用 `pass` 或直接继承父类构造。反射引擎 `ExpressionOps` 会自动解析入参并将它们绑定到实例属性上（例如 `self.feature` 或 `self.N`），并将参数装配进全局统一的 `self.args` 列表中。
- **`*args` 变长参数扁平化规范**：若算子支持变长入参（如 `Concat(*features)`），元拦截器会自动将变长参数扁平化并装填至 `self.args` 中，在 `__str__` 序列化时自动生成形如 `Concat($close,$open,$high)` 的无嵌套圆括号格式。

### 4.3 时序隔离实现规范 (Time-Series Isolation)
所有依赖历史时间窗口（Rolling）或历史偏移量（Ref）的算子，在实现数据加载时，必须具备完善的多股票隔离功能：
```python
def _load_internal(self, df: pd.DataFrame, context: dict = None) -> pd.Series:
    series = self.feature.load(df, context=context)
    # 严格判断是否属于多股票 MultiIndex
    if isinstance(series.index, pd.MultiIndex) and 'ticker' in series.index.names:
        # 分组计算，计算完毕后还原索引层级与排序
        res = getattr(series.groupby(level='ticker').rolling(self.N, min_periods=1), self._func)()
        res = res.droplevel(0)
        return res.reorder_levels(series.index.names).sort_index()
    else:
        # 单股票回退计算
        return getattr(series.rolling(self.N, min_periods=1), self._func)()
```

### 4.4 缓存上下文传递规范 (Context & Caching Propagation)
- 任何算子的 `_load_internal` 方法，其签名必须统一为：
  `_load_internal(self, df: pd.DataFrame, context: dict = None) -> pd.Series`
- 算子内部对子因子调用 `load` 方法时，**必须且只能**穿透向下传递 `context`：
  `series = self.feature.load(df, context=context)`

---

## 📝 5. Formula & Serialization Syntax / 公式表达与序列化规范
为了保证公式的正确解析、序列化及缓存键的唯一性，所有表达式串的处理必须严格遵守下述规范：

- **特征 Token 前缀**：
  - **基础行情列**：前缀为单个美金符号 `$`，如 `$close`、`$open`、`$volume`。
  - **PIT 财务项**：前缀为双美金符号 `$$`，如 `$$revenue`、`$$equity`。
- **序列化字符串格式 (`__str__`)**：
  - 必须由算子类名加上括号构成。
  - 括号内各参数之间**严禁有任何空格**，以逗号 `,` 分隔。
  - 正确的格式示例：`Mean($close,20)`、`Sub(Mean($close,20),1)`。
  - 错误的格式示例：`Mean($close, 20)` (逗号后有空格)、`Mean( $close, 20 )`。

---

## 🧪 6. Testing & Regression Standards / 测试与验证规范
- **测试路径 (Test Directory)**：所有单元测试脚本必须存放在 `sometest/` 目录下，文件命名遵循 `test_*.py` 规则。
- **测试回归要求 (Regression Checks)**：新增任何算子或修改代码后，必须**同时**运行第一阶段的动态反射测试 (`test_reflection.py`) 和第二阶段的时序与缓存测试 (`test_phase2_computations.py`)，确保全套单元测试通过，未发生任何功能退化。
- **终端输出日志格式**：测试输出必须整洁、层次分明，使用明确的日志隔离线和状态 Emoji 标识。
