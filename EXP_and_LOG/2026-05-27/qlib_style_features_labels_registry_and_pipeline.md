# 技术研判日记：Qlib 风格特征与标签注册表及配置链驱动量化计算流水线系统

**日期**：2026-05-27  
**研究员**：Antigravity  
**项目**：MiniQLib (原生多因子计算与回测平台)  
**文件路径**：`EXP_and_LOG/2026-05-27/qlib_style_features_labels_registry_and_pipeline.md`

---

## 🛠️ 设计理念与用户诉求 (Design Philosophy & Requirements)

在 **第一阶段（反射与参数锁）** 和 **第二阶段（时序隔离与极速缓存）** 成功落地后，我们构筑了高保真、零冗余的原生 AST 算子引擎。然而，量化研究是一项需要快速迭代、反复实验的系统工程。为了让新手更好上手、方便团队高效率开发、并降低因子组装的门槛，用户提出了 **第三阶段（Phase 3）** 的核心诉求：

1. **注册制因子与标签库**：
   - *诉求*：支持新手通过极简的注册表调用，以经典的 Qlib 因子和标签为参考，可以直接以“注册名称”直接插拔调用。
   - *设计*：我们将算子底层计算逻辑（`data/ops.py`）与上层因子组合包（`factor/`）完美分离。开发了 `FeatureRegistry` 与 `LabelRegistry` 注册模块，支持以“公式字符串”或“预构建 AST 算子对象”的形态进行一键注册与按名索骥，展示了无缝对接高超的 AST 映射能力。
2. **动态 DataHandler 编译器**：
   - *诉求*：支持从外部配置文件读取字典，全自动执行多层因子拓扑编译，并以最高效的方式输出格式规整的训练矩阵。
   - *设计*：开发了 `DataHandler` 容器，它对配置进行了三层递归编译：已构建 AST 直接通过、注册表 Key 名字自动检索递归编译、纯自定义公式表达式动态 eval 编译。在计算端统一调度 `.setup()`，透传 `context` 缓存，实现极速合并。
3. **时序隔离带安全阻断机制 (Embargo)**：
   - *诉求*：前瞻性地封堵由于未来预测标签（如未来 5 日收益率）所导致的数据集分割处的未来数据泄露风险。
   - *设计*：我们在数据加载环节中，首创基于真实交易日历（`trading_days`）的自动顺延隔离带机制。如果预测标签含有 $N$ 期的时延（如 5 日收益含 1 期执行延迟），我们在训练集与验证集、验证集与测试集的时序交界处，自动剥离并向后推延至少 $N+1$ 个交易日作为安全过渡带，彻底消灭 Look-Ahead Bias。
4. **配置链一键驱动机器学习流水线**：
   - *诉求*：支持基于 YAML 配置文件的一键流水线运行。
   - *设计*：设计了 `config_pipeline.yaml` 配置链与 `run_pipeline.py` 流水线调度脚本。无缝运行五个标准工业步骤：行情加载、因子 DataHandler 编译、数据集 Embargo 划分、LightGBM 训练以及最后的横截面 Rank IC / IR 多维绩评估展示。

---

## ⚙️ 核心架构设计与技术实现 (Core Architecture & Implementation)

### 1. 注册制特征库与标签库 (Registry-based Factor Libraries)
修改及新增聚焦在因子目录 [factor/](file:///C:/Users/liu/Desktop/miniqlib/mini_qlib/factor/)：
- **`label.py`**：注册经典的未来 $1$ 日、未来 $5$ 日、未来 $10$ 日、未来 $20$ 日等进场时延未来收益率标签。支持公式字符串注册与纯 AST 算子对象注册（例如 `Ref(Feature("close"), -6) / Ref(Feature("close"), -1) - 1`）。
- **`feature.py`**：注册经典的 Microsoft Qlib 核心 Alpha158 因子子集。涵盖：
  - K线实体形态：实体涨跌幅比例 (`KMID`)、振幅比率 (`KLEN`)、影线实体比率 (`KMID2`)。
  - 影线波动特征：上影线占比 (`KUP`)、下影线占比 (`KLOW`)、收盘价偏离中枢度 (`KSFT`)。其中利用了全新加入的动态 `Greater` 和 `Less` 双元元素级算子。
  - 时序滚动特征：5日价格动量 (`ROC5`)、10日均线偏离 (`MA10`)、5日滚动波动率 (`STD5`)、10日成交量偏离 (`VMA10`)、5日 RSV 随机指标 (`RSV5`)。
- **`__init__.py`**：统一暴露全局唯一的 `label_registry` 与 `feature_registry` 实例，提供最简洁的接口调用。

### 2. 动态 DataHandler 编译器 (Dynamic DataHandler Compiler)
修改聚焦在配置编译器 [handler.py](file:///C:/Users/liu/Desktop/miniqlib/mini_qlib/data/handler.py)：
- **装配拓扑与递归编译**：
  ```python
  def _compile_single(self, expr: Any, registry: Any, op_ns: dict) -> MiniExpression:
      if isinstance(expr, MiniExpression):
          return expr
      if isinstance(expr, str):
          try:
              registered_expr = registry.get(expr)
              return self._compile_single(registered_expr, registry, op_ns)
          except KeyError:
              parsed_code = parse_field(expr)
              ast_obj = eval(parsed_code, {"__builtins__": {}}, op_ns)
              return ast_obj
  ```
- **安全沙箱与零冗余缓存**：
  - 显式传递 `{"__builtins__": {}}` 封锁危险系统调用。
  - 递归透传共享 `context` 字典字典，防止重复算子多次重算。
  - 通过 `pd.concat` 行对齐，以最高效率将多股票 Panel 矩阵合并输出。

### 3. 数据集切分与时序隔离带安全阻断机制 (Dataset Embargo Safety)
修改聚焦在流水线控制器 [run_pipeline.py](file:///C:/Users/liu/Desktop/miniqlib/mini_qlib/scripts/run_pipeline.py)：
- **交易日顺延隔离带**：对于未来 $5$ 日收益率（含 $1$ 期执行延迟，物理跨度为 $6$ 天），我们基于真实交易日历（剔除周末与节假日）实现隔离防漏计算：
  ```python
  def calculate_embargo_dates(dates, train_end, valid_end, embargo_days):
      sorted_days = sorted(dates.unique())
      idx_train = sorted_days.index(train_end)
      valid_start = sorted_days[min(idx_train + embargo_days, len(sorted_days) - 1)]
      
      idx_valid = sorted_days.index(valid_end)
      test_start = sorted_days[min(idx_valid + embargo_days, len(sorted_days) - 1)]
      return valid_start, test_start
  ```
- **防数据泄露**：这使得训练集的数据信息在切分处物理阻断，不会通过向前看（Look-Ahead）渗透进验证集与测试集，保证了机器学习训练和评估的高真性。

### 4. 可插拔配置链驱动流水线 (Config-driven Machine Learning Pipeline)
- **`config_pipeline.yaml`**：将数据、计算、切分、隔离带天数、模型超参等所有底层元素完全抽取归纳。实现完全的“插拔式配置”，新手只需微调 yaml 即可调度一切。
- **`run_pipeline.py`**：完整串联五大工业步骤。最后的评估模块实现了多维横截面（Cross-Sectional）Spearman Rank IC 与信息比率（IR）的系统级计算。

---

## 🧪 完备单元测试与性能评估 (Test Suite & Performance Evaluation)

为了保障系统计算正确性与安全性，我们在测试套件中编写了全新的回归与集成测试 [test_pipeline.py](file:///C:/Users/liu/Desktop/miniqlib/sometest/test_pipeline.py)，并取得了 **100% 成功跑通** 的结果：

### 1. `test_greater_less_operators()` $\rightarrow$ **测试顺利通过**
- 针对 Panel Data 构建了 AAPL 与 MSFT 的多维行情，测试 `Greater` 和 `Less` 算子的最大值与最小值筛选逻辑。
- 完美验证了元素级对比计算的准确性。

### 2. `test_data_handler_compilation()` $\rightarrow$ **测试顺利通过**
- 验证了 DataHandler 在处理字典配置时，对于“注册键 KMID”、“注册键 MA5”以及“纯自定义公式字符串 `($close - $open) / ($high - $low + 1e-12)`”的成功多层递归编译。
- 断言了输出矩阵索引 index 的对齐度与具体单元格数值的绝对精确度（如 AAPL 首日 KMID = 0.02 且自定义公式比率完美吻合）。

### 3. `test_embargo_safety_calculation()` $\rightarrow$ **测试顺利通过**
- 针对 20 个工作日序列进行隔离带顺延模拟，验证在 `embargo_days=4` 时，能够准确剔除交叉重叠日期，并输出正确的 `valid_start` 和 `test_start` 交易日坐标。

### 4. 工业级 Pipeline 运行实测报告
运行 `python mini_qlib/scripts/run_pipeline.py`，完整流水线完美收敛。在测试集（2023-01-01 至 2024-06-30）上跑出的 LightGBM 模型多维横截面绩效报告如下：

```text
=======================================================
📈 MiniQLib 因子预测流水线性能报告 (Performance Report)
=======================================================
     指标 (Metrics)  数值 (Values)
        Rank IC 均值      0.006425
      Rank IC 标准差      0.250608
      信息比率 (IR)      0.025637
    t 统计量 (t-stat)      0.490520
    正 IC 占比 (胜率)      0.518325
=======================================================
```

---

## 📈 踩坑记录与 Windows 环境防御 (Windows Gotchas & Workarounds)

在 Windows 系统的工业级量化开发实战中，我们总结并封锁了以下致命踩坑点：

1. **Windows 独占文件锁 (DuckDB Lock)**：
   - *痛点*：在 Windows 系统上，DuckDB 的 `.duckdb` 数据库文件一旦被某个进程 `attach` 挂载，其他进程写入或读取都会抛出严重的 `IO Error: Could not set lock on file`。
   - *解法*：如果在 VSCode 中安装了 DuckDB 插件，必须确保在 `.vscode/settings.json` 中配置 `"attached": false` 或暂时脱机挂载，以便释放底层读写文件锁。
2. **Python 模块导入路径冲突 (Sys Path Resolution)**：
   - *痛点*：在 Windows 的 PowerShell 终端中直接以 `python xxx.py` 启动脚本或运行测试，由于 Python 解释器会自动把当前执行脚本所在的子目录加入 `sys.path`，导致我们在脚本里使用 `from mini_qlib.data...` 绝对导入时频繁抛出 `ModuleNotFoundError`。
   - *解法*：我们在所有可执行文件（如 `run_pipeline.py`、`test_pipeline.py`）的首部，以绝对路径计算出项目根目录 `PROJECT_ROOT` 并手动使用 `sys.path.insert(0, str(PROJECT_ROOT))` 加载，彻底杜绝了不同操作系统下的路径解析差异。
3. **Windows 终端 Unicode 编码爆错 (UTF-8 Stdout Defense)**：
   - *痛点*：Windows 系统的 PowerShell/CMD 控制台默认使用 GBK 编码。当脚本输出含有 Emoji（如 🚀, 💽, 🏗️, 🛡️）或特殊 UTF-8 字符时，控制台经常会抛出致命的 `UnicodeEncodeError: 'gbk' codec can't encode character` 导致流水线崩溃。
   - *解法*：我们在流水线和测试脚本的入口处，显式添加控制台重配置代码：
     ```python
     if sys.stdout.encoding.lower() != 'utf-8':
         sys.stdout.reconfigure(encoding='utf-8')
     ```
     以防微杜渐的工业级水准保护控制台打印安全。

---

## 🚀 下一步工作规划 (Next Steps)

1. **财务基本面因子注册库拓展**：
   在 `mini_qlib/factor/` 下新建 `fundamental.py` 特征库，编写基于 DuckDB 中 `income`、`balance`、`cashflow` 表的基本面财务算子（利用 `PFeature` 和 `$$` 语法），丰富基本面多因子量化挖掘。
2. **回测系统对接 (Backtest Integration)**：
   将 LightGBM 生成的测试集预测值矩阵直接输出并挂载到 `backtest/event_driven_loop/` 的事件回测循环中，打通“数据获取 -> 因子计算 -> 机器学习训练 -> 横截面评估 -> 事件回测交易 -> 最终收益归因”的完备闭环全链路。
