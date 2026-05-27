"""
================================================================================
                     MiniQlib Phase 2 Unit Test Harness
================================================================================
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Ensure Windows prints emoji correctly
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Add project root to python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mini_qlib.data.expression import Feature, PFeature, MiniExpression
from mini_qlib.data.ops import ExpressionOps, Mean, Ref, Std, Add, Sub, Div


def test_overflow_and_grouping():
    print("👉 测试 2.1: 跨股票数据时序溢出与分组计算隔离...")
    
    # 构造 Panel Data (MultiIndex: date, ticker)
    dates = pd.date_range('2023-01-01', periods=10)
    tickers = ['AAPL', 'MSFT']
    index = pd.MultiIndex.from_product([dates, tickers], names=['date', 'ticker'])
    
    # AAPL close: 100 to 109
    # MSFT close: 200 to 209
    close_vals = []
    for d in range(10):
        close_vals.append(100.0 + d)  # AAPL
        close_vals.append(200.0 + d)  # MSFT
        
    df = pd.DataFrame({'close': close_vals}, index=index)
    
    close_feat = Feature("close")
    
    # 1. 验证 Ref($close, 1) 的隔离性
    ref_expr = Ref(close_feat, 1)
    res_ref = ref_expr.load(df)
    
    # AAPL 第一天与 MSFT 第一天都应该为 NaN
    aapl_day1 = res_ref.loc[('2023-01-01', 'AAPL')]
    msft_day1 = res_ref.loc[('2023-01-01', 'MSFT')]
    
    assert pd.isna(aapl_day1), f"错误：AAPL 第一天 Ref 结果应为 NaN，实际为 {aapl_day1}"
    assert pd.isna(msft_day1), f"错误：MSFT 第一天 Ref 结果应为 NaN，如果等于 AAPL 的最后一天的值（109.0），则发生时序溢出！实际为: {msft_day1}"
    
    # 验证其他天的值是否正确
    aapl_day2 = res_ref.loc[('2023-01-02', 'AAPL')]
    msft_day2 = res_ref.loc[('2023-01-02', 'MSFT')]
    assert aapl_day2 == 100.0, f"错误：AAPL 第二天 Ref 结果应为 100.0，实际为 {aapl_day2}"
    assert msft_day2 == 200.0, f"错误：MSFT 第二天 Ref 结果应为 200.0，实际为 {msft_day2}"
    
    # 2. 验证 Mean($close, 5) 的隔离性
    mean_expr = Mean(close_feat, 5)
    res_mean = mean_expr.load(df)
    
    # MSFT 前四天均值必须隔离 AAPL 的价格
    # MSFT 第1天: 200.0, 第2天: 201.0
    # MSFT 第2天 Mean (5): (200 + 201)/2 = 200.5
    msft_mean_day2 = res_mean.loc[('2023-01-02', 'MSFT')]
    assert msft_mean_day2 == 200.5, f"错误：MSFT 第二天 Mean 结果应为 200.5，实际为 {msft_mean_day2}"
    
    print("✅ 测试 2.1 顺利通过！")


def test_positional_args_flattening():
    print("\n👉 测试 2.2: 多参数算子 (*args) 扁平化与序列化修复...")
    
    # 自定义多参数算子 MaxOf
    class MaxOf(ExpressionOps):
        def __init__(self, *features):
            pass
            
    close_f = Feature("close")
    open_f = Feature("open")
    high_f = Feature("high")
    
    expr = MaxOf(close_f, open_f, high_f)
    
    # 验证 self.args 是否已被扁平化，并且 str(expr) 没有嵌套的双重圆括号
    assert hasattr(expr, "args"), "错误：MaxOf 算子实例上没有生成 self.args！"
    assert list(expr.args) == [close_f, open_f, high_f], f"错误：self.args 没有被扁平化，实际为: {expr.args}"
    
    expected_str = "MaxOf($close,$open,$high)"
    assert str(expr) == expected_str, f"错误：序列化字符串异常，期待 '{expected_str}'，实际为: '{str(expr)}'"
    
    print("✅ 测试 2.2 顺利通过！")


def test_subexpression_caching():
    print("\n👉 测试 2.3: 零开销因子计算缓存性能与正确性验证...")
    
    # 构造简单的 DataFrame
    dates = pd.date_range('2023-01-01', periods=10)
    df = pd.DataFrame({'close': [float(x) for x in range(100, 110)]}, index=dates)
    
    # 构造复杂表达式：(Mean($close, 5) - $close) / Std($close, 5)
    close_f = Feature("close")
    mean_expr = Mean(close_f, 5)
    std_expr = Std(close_f, 5)
    
    expr = (mean_expr - close_f) / std_expr
    
    # Mock Feature 和 Rolling 的 _load_internal，记录实际计算次数
    feature_call_count = 0
    mean_call_count = 0
    std_call_count = 0
    
    orig_feat_load = Feature._load_internal
    orig_mean_load = Mean._load_internal
    orig_std_load = Std._load_internal
    
    def mock_feat_load(self, df, context=None):
        nonlocal feature_call_count
        feature_call_count += 1
        return orig_feat_load(self, df, context=context)
        
    def mock_mean_load(self, df, context=None):
        nonlocal mean_call_count
        mean_call_count += 1
        return orig_mean_load(self, df, context=context)
        
    def mock_std_load(self, df, context=None):
        nonlocal std_call_count
        std_call_count += 1
        return orig_std_load(self, df, context=context)
        
    # 应用 Mock
    Feature._load_internal = mock_feat_load
    Mean._load_internal = mock_mean_load
    Std._load_internal = mock_std_load
    
    try:
        context = {}
        # 执行计算
        res = expr.load(df, context=context)
        
        # 1. 验证计算结果正确性
        series_close = df['close']
        expected_mean = series_close.rolling(5, min_periods=1).mean()
        expected_std = series_close.rolling(5, min_periods=1).std()
        expected_res = (expected_mean - series_close) / expected_std
        
        pd.testing.assert_series_equal(res, expected_res, check_names=False)
        
        # 2. 验证缓存命中与次数
        # 如果不缓存：
        # - close_f 被 load 了 3 次 (Mean, Sub 右侧, Std)
        # - mean 被 load 了 1 次
        # - std 被 load 了 1 次
        # 在缓存启用下：
        # - close_f 应该只被计算 1 次！
        # - mean 应该只被计算 1 次！
        # - std 应该只被计算 1 次！
        print(f"实际计算次数: Feature={feature_call_count}, Mean={mean_call_count}, Std={std_call_count}")
        assert feature_call_count == 1, f"错误：Feature 因子计算次数应为 1，实际为 {feature_call_count}"
        assert mean_call_count == 1, f"错误：Mean 因子计算次数应为 1，实际为 {mean_call_count}"
        assert std_call_count == 1, f"错误：Std 因子计算次数应为 1，实际为 {std_call_count}"
        
        # 验证 context 中的缓存项数量
        print(f"缓存上下文项数: {len(context)}")
        assert str(close_f) in context
        assert str(mean_expr) in context
        assert str(std_expr) in context
        
    finally:
        # 恢复原始方法
        Feature._load_internal = orig_feat_load
        Mean._load_internal = orig_mean_load
        Std._load_internal = orig_std_load
        
    print("✅ 测试 2.3 顺利通过！")


def test_min_periods_dynamic():
    print("\n👉 测试 2.4: 滚动窗口算子 min_periods 动态参数有效性验证...")
    
    # 构造简单的 DataFrame
    # Construct a simple DataFrame
    dates = pd.date_range('2023-01-01', periods=5)
    df = pd.DataFrame({'close': [10.0, 20.0, 30.0, 40.0, 50.0]}, index=dates)
    
    close_f = Feature("close")
    
    # 1. min_periods=1 (默认情况，前几期应该立刻有值)
    # min_periods=1 (default case, early periods should have values immediately)
    mean_default = Mean(close_f, 3) # N=3
    res_default = mean_default.load(df)
    
    # 验证前两期值不为 NaN / Verify early periods are not NaN
    assert not pd.isna(res_default.iloc[0]), "错误：默认 min_periods=1 时，第一期不应为 NaN！"
    assert not pd.isna(res_default.iloc[1]), "错误：默认 min_periods=1 时，第二期不应为 NaN！"
    assert res_default.iloc[0] == 10.0
    assert res_default.iloc[1] == 15.0 # (10 + 20) / 2
    
    # 2. min_periods=3 (严格模式，前两期应该为 NaN)
    # min_periods=3 (strict mode, early periods should be NaN)
    mean_strict = Mean(close_f, 3, min_periods=3)
    res_strict = mean_strict.load(df)
    
    # 验证前两期必为 NaN，第三期有值
    # Verify early periods are NaN, and the 3rd has value
    assert pd.isna(res_strict.iloc[0]), "错误：严格 min_periods=3 时，第一期必须为 NaN！"
    assert pd.isna(res_strict.iloc[1]), "错误：严格 min_periods=3 时，第二期必须为 NaN！"
    assert res_strict.iloc[2] == 20.0, f"错误：第三期应为 20.0，实际为 {res_strict.iloc[2]}" # (10 + 20 + 30) / 3
    
    # 3. 验证公式唯一字符串包含自定义 min_periods / Verify custom min_periods is in formula string
    assert str(mean_strict) == "Mean($close,3,3)", f"错误：自定义 min_periods 的公式生成异常，实际为: {str(mean_strict)}"
    assert str(mean_default) == "Mean($close,3)", f"错误：默认 min_periods 的公式生成异常，实际为: {str(mean_default)}"
    
    print("✅ 测试 2.4 顺利通过！")


def run_all_tests():
    print("======================================================================")
    print("🚀 开始执行第二阶段：时序溢出、参数扁平化与表达式缓存单元测试")
    print("======================================================================")
    
    test_overflow_and_grouping()
    test_positional_args_flattening()
    test_subexpression_caching()
    test_min_periods_dynamic()
    
    print("\n======================================================================")
    print("🎉 恭喜！第二阶段所有深度计算与优化测试全部顺利通过！")
    print("======================================================================")


if __name__ == "__main__":
    run_all_tests()
