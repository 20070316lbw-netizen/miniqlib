# 2026-05-24 算子引擎设计重构与项目工程化物理拆分记录

## 📌 背景与目标
在开发 `mini_qlib` 算子引擎的过程中，我们希望在复刻微软 Qlib 算子引擎的核心 AST（抽象语法树）计算逻辑的同时，彻底解决 Qlib 中存在的**硬编码痛点**（即避免每新增一个算子，都需要同时改动参数绑定、构造函数以及 `__str__` 字符串化等多处位置）。
为了使整个项目更具有扩展性，并为未来接入大模型（LLM/Model APIs）自动设计因子的白名单与沙箱机制做准备，我们在今天完成了对核心包的重构与物理结构大拆分。

---

## 🔍 核心发现与设计纠偏 (Misunderstanding & Correction)

### 1. 关于 Qlib 原版是否硬编码的真实情况
* **初始理解**：用户与智能体最初都认为，微软 Qlib 的基类（如 `ExpressionOps`）应该采用了类似 `__new__` 的高阶拦截或者动态捕获机制，自动完成了对各算子参数的打包和属性绑定，从而省略了子类的 `__init__` 与 `__str__` 模板代码。
* **深度源码剖析**：对 Qlib 真实克隆源码中 `qlib/qlib/data/base.py` 及 `ops.py` 的深度走读与检索发现，**Qlib 实际上采用了高度硬编码的设计**！
  - 每一个算子（如 `Add`, `Gt`, `Ref`, `Mean`）都显式重写了 `__init__`，手动声明字段绑定。
  - 每个算子都重写了 `__str__` 以拼接它独有的字符串格式。
  - 这种设计导致了巨大的维护成本：算子的入参改动，至少要在构造和字符串化两处进行同步修改，极度臃肿。
* **MiniQlib 的改进方案**：既然我们要超越硬编码，我们在 `mini_qlib` 的 `ExpressionOps` 基类中，策划并实现了**真正的动态参数捕获机制**。采用 `inspect.signature` 反射捕获子类具体的签名，自动执行 `setattr` 属性绑定并装填 `self.args`，真正做到“子类零模板代码，只需写核心计算逻辑”。

### 2. 类级别 `_func` 的设计（来自用户的天才构想）
* **硬编码痛点**：对于滚动窗口算子（如 `Mean(Rolling)`），最初的设计依然需要在子类的构造函数中，通过 `super().__init__(feature, N, "mean")` 来硬编码传递统计指标字串。
* **高阶重构**：用户提出将此字串转化为**类级属性** `_func = "mean"` 声明于类定义最顶部。
* **实现方式**：
  ```python
  class Mean(Rolling):
      _func = "mean"  # 类级别属性，直观明了
  ```
  `Rolling` 基类在 `__init__` 时通过反射机制读取当前子类的 `self._func` 自动完成底层 Pandas rolling 函数的动态映射。这彻底消除了 `super().__init__` 中传递硬编码字串的开销。

---

## 🛠️ 项目物理大重构与成果汇总

### 1. AST 地基剥离：`expression.py` 从 `ops.py` 中拆分
* **问题描述**：将 AST 的运算符重载地基（`MiniExpression`）和具体算子堆砌在同一个 `ops.py` 中，会导致未来的算子代码极其冗长混乱，且在子算子之间由于魔法方法的相互调用产生严重的**循环导入（Circular Import）**风险。
* **重构方案**：
  - 新建 [mini_qlib/data/expression.py](file:///c:/Users/liu/Desktop/miniqlib/mini_qlib/data/expression.py)，作为纯粹的 AST 树叶子与根节点地基类（只保留 `MiniExpression`, `Feature`, `PFeature` 以及比较运算符重载）。
  - [mini_qlib/data/ops.py](file:///c:/Users/liu/Desktop/miniqlib/mini_qlib/data/ops.py) 专门从地基中导入核心类，实现纯粹的算子族逻辑。

### 2. 因子包独立与大模型白名单安全规划
* **重构方案**：创建独立的 [mini_qlib/factor](file:///c:/Users/liu/Desktop/miniqlib/mini_qlib/factor) 包，用于隔离因子定义与引擎底层。
* **白名单（Whitelist）与沙箱（Sandbox）规划**：
  - 由于系统未来会接入 Open AI、Anthropic 等模型 API，由 LLM 生成因子公式字符串并运行 `eval(parse_field(expr))` 存在严重的代码注入安全隐患。
  - 我们在此包中规划了白名单防御层，所有 LLM 输入必须经过合法算子白名单检验；同时限制嵌套深度和 $N$ 的取值范围，提供稳健计算沙箱。

### 3. 根目录 Agent 工程容器建立
* **重构方案**：在根目录下建立了独立于业务的 [agent/](file:///c:/Users/liu/Desktop/miniqlib/agent) 文件夹，用于后续存放 AI Agent 研报自动生成器、Prompt 提示词模板及大模型 Function Calling 的 Tool 定义。

### 4. 数据库安全迁移与 VSCode 环境兼容
* **问题描述**：原 7.6MB 的标普 500 财务大数据库 `edgar.duckdb` 遗留在工作区根目录，导致物理结构混乱；同时 VSCode 的 DuckDB 数据浏览器插件锁定了旧的路径，直接迁移会导致 VSCode 报错。
* **解决策略**：
  1. 通过 PowerShell 将 `edgar.duckdb` 彻底移入专职数据存储仓 [mini_qlib/database/](file:///c:/Users/liu/Desktop/miniqlib/mini_qlib/database)。
  2. 同步更新了 [.vscode/settings.json](file:///c:/Users/liu/Desktop/miniqlib/.vscode/settings.json)，修改 attached 库路径至新版相对路径 `./mini_qlib/database/edgar.duckdb`，完美保证了 VSCode 插件一键打开数据库查询的兼容性。
  3. 修改了财务报表下载器 [fetch_edgar_runner.py](file:///c:/Users/liu/Desktop/miniqlib/mini_qlib/scripts/fetch_edgar_runner.py) 中的 `DB_PATH` 为基于 `PROJECT_ROOT` 推导的稳健路径，彻底排除执行环境的工作目录差异隐患。

### 5. 补充物理 README 沉淀 Point-in-Time (PIT) 原理
* 我们为所有目录补充了全面、双语且图文并茂的 README.md 说明。
* **最具含金量的成果**：在 [database/README.md](file:///c:/Users/liu/Desktop/miniqlib/mini_qlib/database/README.md) 中详细记录并科普了 **Point-in-Time (PIT) 时点数据机制**，阐明了双时间戳（财报期末日 `period_end` 与 真实递交公布日 `filed`）对于杜绝回测中“未来函数/前瞻偏差（Look-Ahead Bias）”的核心作用，作为本项目的极佳知识沉淀。

---

## 🔮 未来探索规划
本轮大重构完美理清了整个量化分析软件的物理和逻辑层级。明天我们将以此清晰、优雅、安全的架构为基石，正式进军各算子内部的具体 Pandas 并行滚动计算实现！
