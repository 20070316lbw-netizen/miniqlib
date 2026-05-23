# Data & Operator Engine Module / 因子与算子计算引擎

## 📌 Introduction / 简介
本模块是 `mini_qlib` 最核心的**计算图引擎**所在地。它负责承载数据的读取、缓存管理、因子公式的解析编译，以及利用 Python 运算符重载机制动态构建多维抽象语法树（AST）进行因子并行计算。

---

## 📂 Core Files / 核心文件职责
1. **`expression.py` (计算树地基)**：
   - 包含底层计算树的节点基类 `MiniExpression`，定义了全套的四则运算与逻辑比较重载方法。
   - 包含原子变量特征类 `Feature`（对应 `$close` 静态列）与 `PFeature`（对应 `$$revenue` 的时点基本面数据）。
   - 将地基单独剥离，彻底消除了具体算子继承时的循环导入（Circular Import）隐患。
2. **`ops.py` (算子大本营)**：
   - 包含各种高阶表达式算子（如滚动均值 `Mean`、历史引用 `Ref`、条件选择 `If` 等）。
   - 实现了高阶的**动态参数反射绑定机制**（`ExpressionOps`），子类自动绑定入参并生成唯一公式字符串（例如 `Ref($close, 1)`），无需任何手动序列化与 `__init__` 参数绑定的硬编码。
   - 子类滚动算子通过声明类级属性 `_func = "mean"` 自动将底层计算委托给父类 `Rolling`，做到“一处定义，处处生效”。
3. **`load_data.py` (数据加载底座)**：
   - 提供直接面向 DuckDB 的底层读取接口。
   - 实现了价格行情的增量写入合并逻辑，作为计算引擎的行情数据源泉。

---

## 🔄 Computational Flow / 计算图运行机制
1. **输入解析**：用户输入的文本公式 `"$close - Ref($open, 1)"` 通过 `parse_field()` 函数被正则映射为 Python 可执行代码字符串 `"Feature('close') - Operators.Ref(Feature('open'), 1)"`。
2. **AST 动态构建**：利用 `eval()` 运行该代码，由于 `Feature` 继承自 `MiniExpression`，其重载的减法运算符 `__sub__` 会自动捕获右边的 `Ref` 算子实例，并在内存中组装成一颗拥有三个节点的 AST 树。
3. **扩展时间窗口**：引擎调用树根的 `get_extended_window_size()`，递归计算出该计算链在左侧历史需要多读 1 天的数据（用于处理 `Ref` 的 N=1 位移），从而拉取 `[start - 1, end]` 的行情。
4. **加载与计算**：
   - 基础特征 `Feature` 从数据库拉取数据序列。
   - `Ref` 节点接收其子节点的序列，并执行 `.shift(1)` 滚动操作。
   - 减法节点 `Sub` 执行行级减法，最终裁剪掉头部多读的 1 天临时数据，将完全无 NaN 的干净序列返回给上层策略！
