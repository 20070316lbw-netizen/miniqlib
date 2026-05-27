# 测试覆盖增强方案 (Test Coverage Improvement Plan)

> 创建日期: 2026-05-27
> 关联审计: MiniQLib 核心代码审计报告 P5
> 当前状态: 待执行 (Pending Execution)

---

## 一、现状评估 (Current State Assessment)

### 已有测试 (Existing Tests)

| 测试文件 | 覆盖内容 | 行数 | 状态 |
| :--- | :--- | :--- | :--- |
| `sometest/test_reflection.py` | 动态反射参数捕获、AST 拓扑、多级继承锁、公式编译器 | ~150 | ✅ PASSING |
| `sometest/test_phase2_computations.py` | 跨股票时序隔离、`*args` 扁平化、子表达式缓存、min_periods | ~236 | ✅ PASSING |
| `sometest/test_pipeline.py` | 流水线集成（待确认内容） | ? | ⚠️ 待验证 |
| `sometest/test_backtest.py` | 回测引擎（待确认内容） | ? | ⚠️ 待验证 |

### 覆盖缺口 (Coverage Gaps)

| 缺口编号 | 目标模块 | 缺失的测试项 | 风险等级 |
| :--- | :--- | :--- | :--- |
| G1 | `expression.py` | `PFeature` 时点特征算子 | 🟡 中 |
| G2 | `ops.py` | `If` 三目条件算子 | 🟡 中 |
| G3 | `ops.py` | `Log` / `Sign` / `Abs` 单目算子的边界值（负数、零） | 🟢 低 |
| G4 | `ops.py` | `Greater` / `Less` 元素级双目标量算子 | 🟢 低 |
| G5 | `ops.py` | `NpPairOperator` 多股票 MultiIndex 下的嵌套计算 | 🟡 中 |
| G6 | `handler.py` | `DataHandler._compile_single` 异常路径（KeyError、eval 失败、类型错误） | 🔴 高 |
| G7 | `handler.py` | `DataHandler.setup` 端到端因子矩阵生成 | 🔴 高 |
| G8 | `handler.py` | eval 沙箱安全性回归测试（确认 `__builtins__` 被锁死） | 🔴 高 |
| G9 | `backtest/` | 回测完整集成：多日撮合 + 持仓更新 + NAV 计算 | 🔴 高 |
| G10 | `backtest/` | T+1 因果律断言验证 | 🟡 中 |
| G11 | `backtest/` | `Exchange.match_orders` 流动性上限（partial fill）和现金不足兜底 | 🟡 中 |
| G12 | `backtest/` | `DataPortal.get_history` 截断逻辑 | 🟡 中 |
| G13 | `factor/` | `FeatureRegistry` / `LabelRegistry` 注册、获取、重复注册 | 🟡 中 |
| G14 | `factor/` | 标签公式（如 `Ref($close, -6)` 负偏移）在 MultiIndex 下的计算正确性 | 🔴 高 |

---

## 二、补测方案 (Remediation Plan)

### Phase A: 单算子边界补充测试 (Priority: 中, 预估 1h)

**文件**: `sometest/test_operators_edge_cases.py`

```python
# 覆盖 G2, G3, G4, G5

class TestSingleOperators:
    def test_log_negative_handles_nan(self):
        """Log 对负数和零应返回 NaN 而非抛异常"""
    
    def test_sign_zero_returns_zero(self):
        """Sign(0) 应返回 0"""
    
    def test_abs_negative_returns_positive(self):
        """Abs 对负数应返回正数"""

class TestIfOperator:
    def test_if_condition_true_returns_left(self):
        """If 条件为真时返回 left 分支"""
    
    def test_if_condition_false_returns_right(self):
        """If 条件为假时返回 right 分支"""
    
    def test_if_mixed_scalar_series(self):
        """If 分支中混合标量和 Series"""

class TestNpPairOperatorMultiStock:
    def test_add_two_stocks_rolling_mean(self):
        """Add(Mean($close,5), Mean($open,5)) 在两只股票的 MultiIndex 下正确对齐"""
```

### Phase B: DataHandler 编译器与沙箱测试 (Priority: 高, 预估 1.5h)

**文件**: `sometest/test_data_handler.py`

```python
# 覆盖 G6, G7, G8

class TestDataHandlerCompilation:
    def test_compile_registry_feature(self):
        """从 FeatureRegistry 按名索骥编译 KMID"""
    
    def test_compile_custom_formula_string(self):
        """自定义公式字符串编译为 AST 对象"""
    
    def test_compile_prebuilt_ast_object(self):
        """预构建 AST 对象直接通过"""
    
    def test_compile_unknown_key_falls_back_to_formula(self):
        """不在注册表中的字符串自动按公式编译"""
    
    def test_compile_invalid_formula_raises_valueerror(self):
        """无效公式字符串抛出 ValueError"""
    
    def test_compile_non_string_non_ast_raises_typeerror(self):
        """非字符串非 AST 类型抛出 TypeError"""

class TestDataHandlerEvalSandbox:
    def test_eval_blocks_builtins(self):
        """确认 eval 沙箱中 __builtins__ 为空，__import__ 不可用"""
    
    def test_eval_blocks_os_system(self):
        """确认 eval 沙箱中无法调用 os.system"""
    
    def test_eval_blocks_open(self):
        """确认 eval 沙箱中无法调用 open"""

class TestDataHandlerSetup:
    def test_setup_returns_correct_columns(self):
        """setup() 返回的 DataFrame 列名与配置一致"""
    
    def test_setup_preserves_multiindex(self):
        """setup() 返回的 DataFrame 保留原始 MultiIndex"""
    
    def test_setup_with_cache_context(self):
        """传入 context 字典时正确共享缓存"""
```

### Phase C: 回测引擎集成测试 (Priority: 高, 预估 2h)

**文件**: `sometest/test_backtest_integration.py`

```python
# 覆盖 G9, G10, G11, G12

class TestBacktestIntegration:
    def test_full_cycle_two_stocks_two_days(self):
        """两只股票两天完整撮合-估值-调仓周期"""
    
    def test_t_plus_one_enforcement(self):
        """T日下单只能在 T+1 日成交"""
    
    def test_liquidity_cap_partial_fill(self):
        """成交量上限导致部分成交"""
    
    def test_cash_insufficient_auto_scale_down(self):
        """现金不足时自动缩量买入"""
    
    def test_sell_stamp_tax_applied(self):
        """卖出端正确扣除印花税"""
    
    def test_nav_calculation_with_suspended_stock(self):
        """停牌股票估值回退为成本价"""

class TestDataPortal:
    def test_get_history_truncates_future(self):
        """get_history 不返回未来日期数据"""
    
    def test_get_current_returns_nan_for_missing(self):
        """缺失数据返回 NaN 而非抛异常"""
    
    def test_get_history_returns_empty_for_unknown_ticker(self):
        """未知 ticker 返回空 Series"""
```

### Phase D: 因子/标签注册表测试 (Priority: 中, 预估 0.5h)

**文件**: `sometest/test_registry.py`

```python
# 覆盖 G13, G14

class TestFeatureRegistry:
    def test_register_and_get(self):
        """注册后可通过名称获取"""
    
    def test_get_unregistered_raises_keyerror(self):
        """获取未注册项抛出 KeyError"""
    
    def test_list_all_returns_names(self):
        """list_all 返回所有已注册名称"""

class TestLabelComputation:
    def test_label_5d_negative_ref_multistock(self):
        """Ref($close, -6) 在两只股票下正确隔离计算"""
    
    def test_label_1d_gap_handling(self):
        """1日标签的 gap 处理正确（t+1买入，t+2卖出）"""
```

---

## 三、执行顺序 (Execution Order)

按风险等级和依赖关系排列：

1. **Phase B** (DataHandler 沙箱 + 编译) — 当前测试缺口最大，安全风险最高
2. **Phase C** (回测集成) — 回测是面向用户的最终输出，必须保证正确性
3. **Phase D** (注册表 + 标签) — 因子库的可用性保障
4. **Phase A** (算子边界) — 低风险补充，可最后执行

---

## 四、回归测试检查清单 (Regression Checklist)

修改任何 `data/` 或 `backtest/` 下的代码后，必须运行以下全部测试：

- [ ] `sometest/test_reflection.py` — 反射与参数锁
- [ ] `sometest/test_phase2_computations.py` — 时序隔离与缓存
- [ ] `sometest/test_operators_edge_cases.py` — 算子边界（待创建）
- [ ] `sometest/test_data_handler.py` — DataHandler（待创建）
- [ ] `sometest/test_registry.py` — 注册表（待创建）
- [ ] `sometest/test_backtest_integration.py` — 回测集成（待创建）
