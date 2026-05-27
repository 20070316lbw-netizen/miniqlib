# 块状循序渐进式代码审计方法与智能体规范 (Sequential Code Auditing & Agent Rules)

为了确保 `MiniQLib` 工作区的代码质量、架构规范及回测系统的绝对高保真（防止数据泄露与前瞻偏差），我们在此定义了一套**由用户主导、智能体深度配合的块状循序渐进式代码审计方法论**。同时，本文件完整继承并升级了原本智能体的核心开发规则。

---

## 🔍 一、块状循序渐进式代码审计方法 (Sequential Auditing Methodology)

在后续的审计过程中，我们将采用**“用户按块提问，智能体深度透视”**的交互模式。具体审计规范如下：

### 1. 交互流程 (Workflow)
* **用户输入**：用户将分模块、分文件或分段（通常以 50-200 行为一个逻辑块）向智能体展示代码或提问。
* **智能体响应**：智能体在分析每一块代码时，必须进行**全方位立体化透视**，绝不进行肤浅的表面回答。

### 2. 智能体审计检查点 (Agent Auditing Checkpoints)
针对用户展示的每一个代码块，智能体必须强制检查并深度解析以下维度：
* ⚠️ **未来函数与数据泄露 (Look-Ahead Bias & Data Leakage)**：对于回测和数据处理核心代码，必须严密审查是否存在任何时序上的“前瞻偏差”或跨股票边界的“数据污染”。
* 🏗️ **架构合理性与类继承设计 (Architectural & Inheritance Integrity)**：审查类的继承链是否清晰，是否存在参数覆盖、不必要的强耦合或设计模式层面的坏味道。
* 🛡️ **异常边界与鲁棒性校验 (Error Handling & Robustness)**：检查是否遗漏了必要的输入验证、边界条件（如空值、NaN、无穷大）以及异常捕获。
* 🌐 **双语注释契约 (Bilingual Commenting Compliance)**：严格检查代码的 docstring 和行内注释是否符合“英上中下”的对照翻译要求。
* 💾 **UTF-8 编码防线 (UTF-8 Encoding Defense)**：检查凡是涉及文件 I/O 的方法是否明确指定了 `encoding="utf-8"`。
* 🚀 **性能瓶颈与矢量化空间 (Performance & Vectorization)**：分析是否存在不合理的 Python 级 `for` 循环，是否有使用 NumPy、Pandas 矢量化或 Numba 加速的重构空间。

### 3. 改进建议输出标准 (Recommendations Formatting)
* 当智能体在审计中发现任何设计缺陷、安全隐患或规范偏差时，**必须提供清晰易读的 Diff 格式修改建议**，方便用户评估和一键集成。
* 绝不使用模糊的描述，必须明确指出文件名、起始行号及精确代码。

---

## 📜 二、智能体核心开发规则 (Core Agent Rules - Inherited & Upgraded)

智能体在协助用户进行代码审查、重构与新代码编写时，必须无条件遵守以下开发规则：

### 1. 默认沟通语言 (Preferred Language)
* 与用户交流时，默认使用**中文（zh-CN）**进行专业、谦逊且高效的解答。
* 所有的工件（如 `implementation_plan.md`、`task.md`、`walkthrough.md`）必须默认使用中文编写。

### 2. 文件顶部 ASCII 架构图规范 (File Header Architecture Diagrams)
* 每一个核心代码文件（包括算子引擎基类、具体算子、数据加载、财务抓取解析等）的顶部，**必须包含一个用 ASCII/文本字符绘制的清晰架构/流程关系图**。
* 该图应直观展现本文件核心类的继承体系、主要数据流动方向或方法调用链路，极大提升代码的视觉表现力与可读性。

### 3. 踩坑与实验记录机制 (Experiment & Issue Logging)
* 无论在开发或审计中遇到了任何技术瓶颈、架构重构抉择、纠正设计误区或进行探索性实验，**必须在 `EXP_and_LOG/<YYYY-MM-DD>/` 下新建 Markdown 记录**。
* 实验日志应详细记录：**问题现象、底层深度成因、备选方案对比、最终架构决策**。

### 4. 双语注释并重契约 (Bilingual Commenting Contract)
* 所有编写或重构的代码，其 docstrings、模块说明、关键行代码注释**必须采用英文与中文双语对照编写**（英文在上，精确中文在下），并遵循 `agent/translator.md` 的规范。

---

## 📅 三、全套代码审计路线图 (Audit Roadmap Summary)
根据根目录 `README.md`，我们将依次审计以下 6 个核心阶段：
1. **Phase 1: AST 核心代数表示层** (`mini_qlib/data/expression.py`)
2. **Phase 2: 核心算子时序隔离与反射层** (`mini_qlib/data/ops.py`)
3. **Phase 3: 数据加载、处理与沙箱编译层** (`mini_qlib/data/load_data.py`, `mini_qlib/data/handler.py`)
4. **Phase 4: EDGAR 真实财务数据抓取解析层** (`mini_qlib/fetcher/fetch_edgar.py`, `mini_qlib/fetcher/fetch_price.py`, `mini_qlib/fetcher/get_sp_500_list.py`)
5. **Phase 5: 业务调度与系统配置加载层** (`mini_qlib/scripts/fetch_data.py`, `mini_qlib/scripts/fetch_edgar_runner.py`, `mini_qlib/utils/config.py`)
6. **Phase 6: 单元测试与高保真运行校验层** (`sometest/test_reflection.py`, `sometest/test_phase2_computations.py`)
