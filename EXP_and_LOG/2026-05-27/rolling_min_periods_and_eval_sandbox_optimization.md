# 技术研判日记：滚动窗口算子动态窗口控制与因子沙箱安全隔离系统级升级

**日期**：2026-05-27  
**研究员**：Antigravity  
**项目**：MiniQLib (原生多因子计算与回测平台)  
**文件路径**：`EXP_and_LOG/2026-05-27/rolling_min_periods_and_eval_sandbox_optimization.md`

---

## 🛠️ 优化背景与用户诉求

在 **第一阶段（反射与参数锁）** 和 **第二阶段（时序隔离与极速缓存）** 圆满成功的基础上，我们在对 `mini_qlib` 原生核心代码进行全面深度审计与审查时，识别出了两处极具前瞻性的优化与安全性漏洞收窄机会：

1. **`min_periods` 动态窗口控制**：
   - *旧痛点*：原先的滚动时间序列算子（如 `Mean`、`Std`、`Sum` 等）在继承基类 `Rolling` 时，底层的 pandas `.rolling()` 计算中 `min_periods` 均被硬编码为了 `1`。
   - *隐患*：虽然前几期立刻产出非空计算值在某些情况下较实用，但在严格的因子表现测试中，时间序列前段未成熟的数据点（例如在滚动均线 $N=60$ 时，前 5 日的非空均价）具有极高的数据噪音。量化研究员迫切需要支持动态设置 `min_periods`（例如严格要求 `min_periods=N`），以在时序上进行更为精准和严格的缺失值阻断。
2. **`eval()` 任意代码执行漏洞防范**：
   - *旧痛点*：`DataHandler` 编译器为了实现可插拔配置与极速公式编译，使用了 `eval(parsed_code, {}, op_ns)` 来动态将字符串转换为 AST 计算图。
   - *隐患*：尽管公式输入目前是来自受信任的内部 YAML 配置文件，但在工业级部署或多终端研究环境下，直接开放无限制的 `eval()` 权限是一项极其危险的任意代码执行隐患（如通过 `__import__` 导入系统 `os` 库执行越权破坏）。我们急需在不影响公式数学运算的前提下，收窄其名字空间访问权限。

用户高度认可了以上两个优化方向并下达了实现指令，本篇文档记录了针对这两个核心改进的工业级技术设计与无损验证全过程。

---

## ⚙️ 技术设计与工业级实现

### 1. 滚动窗口算子动态 `min_periods` 的优雅实现
修改主要聚焦在算子核心集合库 [ops.py](file:///C:/Users/liu/Desktop/miniqlib/mini_qlib/data/ops.py)：

#### 构造函数形参改造与自动反射捕获
我们为 `Rolling` 基类添加了显式的可选参数 `min_periods: int = 1`：
```python
class Rolling(ExpressionOps):
    # ...
    def __init__(self, feature: MiniExpression, N: int, min_periods: int = 1):
        # 拦截包装器会自动绑定 self.feature = feature, self.N = N, self.min_periods = min_periods
        pass
```
由于其派生类（如 `Mean`）均未定义自定义 `__init__` 构造器，因此会自动继承该包装方法，无需在各子类中硬编码任何参数捕获，完美继承了 `ExpressionOps` 动态反射的架构美感。

#### 底层计算时序控制改造
在 `Rolling._load_internal` 方法中，将滚动计算时硬编码的 `min_periods=1` 动态替换为 `min_periods=self.min_periods`：
```python
    def _load_internal(self, df: pd.DataFrame, context: dict = None) -> pd.Series:
        series = self.feature.load(df, context=context)
        if isinstance(series.index, pd.MultiIndex) and 'ticker' in series.index.names:
            # groupby ticker 并进行 rolling 计算，然后用 droplevel 和 reorder_levels 还原索引与排序
            res = getattr(series.groupby(level='ticker').rolling(self.N, min_periods=self.min_periods), self._func)()
            res = res.droplevel(0)
            return res.reorder_levels(series.index.names).sort_index()
        else:
            return getattr(series.rolling(self.N, min_periods=self.min_periods), self._func)()
```

#### 条件式最简序列化与向下兼容性 (`__str__`)
如果 `min_periods` 在实例化时未传（默认为 `1`），那么公式字符串应当与先前格式完美一致以规避不必要的缓存 Key 膨胀。如果被显式设置为自定义值（如 `Mean($close, 3, 3)`），则必须区别序列化。
我们在 `Rolling` 类中自定义重写了 `__str__` 魔法方法：
```python
    def __str__(self) -> str:
        """
        根据 min_periods 是否为默认值 1，动态生成最简公式字符串。
        """
        if hasattr(self, 'min_periods') and self.min_periods != 1:
            return f"{type(self).__name__}({self.feature},{self.N},{self.min_periods})"
        return f"{type(self).__name__}({self.feature},{self.N})"
```
- **向下兼容**：`Mean($close, 20)` 与原先保持绝对一致，完美匹配现有 Qlib 配置以及单元测试。
- **缓存安全**：若设置为不同的观测数（如 `min_periods=20`），公式字符串自动调整为 `Mean($close,20,20)`。这能作为唯一的 `context` 缓存键，在计算图物理上彻底将两者隔离开来，防止严重的因子缓存碰撞污染。

---

### 2. `eval()` 沙箱化高强度安全防线
修改聚焦在配置编译器 [handler.py](file:///C:/Users/liu/Desktop/miniqlib/mini_qlib/data/handler.py)：

#### Built-ins 名字空间收窄
在 `DataHandler._compile_single` 中，我们将 `eval` 编译时的 globals 参数由空字典 `{}` 替换为显式限制的 `{"__builtins__": {}}`：
```python
                    # eval 编译，将字符串实例化为 AST 树，并禁用 __builtins__ 以防止任何恶意代码注入
                    ast_obj = eval(parsed_code, {"__builtins__": {}}, op_ns)
```
- **安全效果**：此时，在 eval 环境内无法使用任何 Python 内置方法（包括 `__import__`、`open`、`exec`、`eval`、`getattr` 等系统调用），彻底将输入公式的作用域封锁在了**“无毒数学运算与纯 AST 算子实例组装”**的纯净沙箱内。
- **因子兼容**：由于所有的数学逻辑计算（如 `+`、`-`、`*`、`/` 等重载）和算子类均由 `op_ns` 提供，因子的表达式编译没有任何性能和功能损失。

---

## 🧪 完备单元测试与无损回归验证

为了全面验证两项重要改动的正确性，我们在测试套件中补充了全新的断言，并重新跑通了第一、第二、第三阶段的全部单元测试与冒烟流水线：

### 1. `test_reflection.py`（第一阶段） $\rightarrow$ **100% 成功跑通**
- 验证了 ExpressionOps 反射机制完美适应 `Rolling` 构造器新加的 `min_periods` 参数。
- 修改了 `mean_op.args` 期望断言为 `[close_feature, 20, 1]`，验证了 `inspect.signature` 抓取默认值的准确性。

### 2. `test_phase2_computations.py`（第二阶段） $\rightarrow$ **100% 成功跑通**
我们新编写了针对滚动观测窗口有效性的专属单元测试 `test_min_periods_dynamic()`：
- **默认控制组 (`min_periods=1`)**：对于长度为 5 的序列，前两期能够正常返回结果（第一期为 `10.0`，第二期为 `15.0`）。
- **动态实验组 (`min_periods=3`)**：测试了在前两期，计算结果在时序上被**严格阻断并输出为 `NaN`**，只有在第三期累积够 3 个有效观测点时，才计算并产出正常的值 `20.0`。
- **公式验证组**：对 `Mean($close,3,3)` 与 `Mean($close,3)` 的公式字符串差异进行了精准断言，证实两者空间完全被隔开。

### 3. `test_pipeline.py`（第三阶段） $\rightarrow$ **100% 成功跑通**
- 证实了沙箱化的 `eval()` 能够完美在限制名字空间权限的前提下，编译、结算并对齐所有的 Handler 配置因子矩阵。

### 4. 工业级 Pipeline 与 Corn 3D 对比实验 $\rightarrow$ **100% 成功跑通**
- 跑通配置链驱动流水线：`run_pipeline.py` 运行时，数据编译、Embargo 数据切分、LightGBM 训练以及最后的横截面绩效 Rank IC / IR 全部在最新的安全沙箱中完美执行完毕。
- 跑通 3D LambdaRank 实验：`corn.py` 成功读取数据库行情，顺次跑完 baseline、exp_A 和 exp_B 的对比测试，并在终端打印出了高保真绩效分析报表。

---

## 📈 工程启示与规范沉淀

1. **量化反射的向下兼容性最佳实践**：
   在为基础通用算子增添高级可选属性时，应当始终通过像重写 `__str__` 这样的细节，在默认情况下输出“最简 canonical 公式字串”。这极大地保护了历史缓存命中率，同时又极具逻辑优雅性。
2. **永远警惕配置动态解析的潜在漏洞**：
   在任何涉及从配置文件（YAML/JSON）或外部网络加载公式或配置的系统设计中，永远应该用 `{"__builtins__": {}}` 锁紧 `eval()` 的调用。这是一种几乎“零成本”但收益无比巨大的极佳工程安全规范。
