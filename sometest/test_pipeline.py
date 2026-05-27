"""
================================================================================
                    MiniQLib Phase 3 Automated Test Harness
================================================================================
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Ensure Windows prints emoji correctly
try:
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, OSError):
    pass

# Add project root and package root to python path to prevent ModuleNotFoundError
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "mini_qlib"))

from mini_qlib.data.expression import Feature, MiniExpression
from mini_qlib.data.ops import Greater, Less, parse_field, get_op_namespace
from mini_qlib.data.handler import DataHandler
from mini_qlib.factor import label_registry, feature_registry
from mini_qlib.scripts.run_pipeline import calculate_embargo_dates


def test_greater_less_operators():
    print("👉 测试 3.1: 动态 Greater 和 Less 元素级算子计算正确性...")
    
    # 构造 Panel Data (MultiIndex: date, ticker)
    dates = pd.date_range('2024-01-01', periods=3)
    tickers = ['AAPL', 'MSFT']
    index = pd.MultiIndex.from_product([dates, tickers], names=['date', 'ticker'])
    
    # AAPL open: 100, close: 105 (close > open)
    # MSFT open: 200, close: 195 (open > close)
    df = pd.DataFrame({
        'open':  [100.0, 200.0, 101.0, 201.0, 102.0, 202.0],
        'close': [105.0, 195.0, 99.0,  205.0, 106.0, 200.0]
    }, index=index)
    
    open_feat = Feature("open")
    close_feat = Feature("close")
    
    # 1. 验证 Greater
    greater_expr = Greater(open_feat, close_feat)
    res_greater = greater_expr.load(df)
    
    # AAPL day 1: max(100, 105) = 105.0
    # MSFT day 1: max(200, 195) = 200.0
    assert res_greater.loc[('2024-01-01', 'AAPL')] == 105.0
    assert res_greater.loc[('2024-01-01', 'MSFT')] == 200.0
    
    # 2. 验证 Less
    less_expr = Less(open_feat, close_feat)
    res_less = less_expr.load(df)
    
    # AAPL day 1: min(100, 105) = 100.0
    # MSFT day 1: min(200, 195) = 195.0
    assert res_less.loc[('2024-01-01', 'AAPL')] == 100.0
    assert res_less.loc[('2024-01-01', 'MSFT')] == 195.0
    
    print("✅ 测试 3.1 顺利通过！")


def test_data_handler_compilation():
    print("\n👉 测试 3.2: DataHandler 动态配置解析与 AST 组装计算...")
    
    # 构造 Panel Data
    dates = pd.date_range('2024-01-01', periods=10)
    tickers = ['AAPL', 'MSFT']
    index = pd.MultiIndex.from_product([dates, tickers], names=['date', 'ticker'])
    
    df = pd.DataFrame({
        'open':  [100.0 + x for x in range(20)],
        'close': [102.0 + x for x in range(20)],
        'high':  [105.0 + x for x in range(20)],
        'low':   [98.0 + x for x in range(20)],
        'volume': [1000 + x * 10 for x in range(20)]
    }, index=index)
    
    # 自定义一个可插拔配置字典
    handler_config = {
        "features": {
            "MY_KMID": "KMID",                                         # 注册表中
            "MY_MA5": "MA5",                                           # 注册表中
            "CUSTOM_DIFF": "($close - $open) / ($high - $low + 1e-12)" # 纯自定义公式
        },
        "labels": {
            "my_label": "label_1d"                                     # 注册表中
        }
    }
    
    handler = DataHandler(df, handler_config)
    res_df = handler.setup()
    
    # 1. 验证输出的 columns 和 Index 对齐
    assert set(res_df.columns) == {"MY_KMID", "MY_MA5", "CUSTOM_DIFF", "my_label"}
    pd.testing.assert_index_equal(res_df.index, df.index)
    
    # 2. 验证计算数值的准确性 (拿第一只股票 AAPL 手工算以核对)
    # KMID = (close - open) / open
    # AAPL day 1: open=100.0, close=102.0. KMID = 2 / 100 = 0.02
    assert np.isclose(res_df.loc[('2024-01-01', 'AAPL'), 'MY_KMID'], 0.02)
    
    # CUSTOM_DIFF = (102 - 100) / (105 - 98) = 2 / 7 = 0.285714...
    assert np.isclose(res_df.loc[('2024-01-01', 'AAPL'), 'CUSTOM_DIFF'], 2 / 7)
    
    print("✅ 测试 3.2 顺利通过！")


def test_embargo_safety_calculation():
    print("\n👉 测试 3.3: 隔离带 (Embargo) 时序切分防止未来信息泄露...")
    
    # 构造真实的连续交易日列表 (20 个交易日)
    dates = pd.date_range('2024-01-01', periods=20, freq='B')
    
    train_end = pd.Timestamp(dates[10]) # 训练集在第 10 天结束
    valid_end = pd.Timestamp(dates[15]) # 验证集在第 15 天结束
    
    embargo_days = 4 # 设定 4 个交易日的隔离带
    
    valid_start, test_start = calculate_embargo_dates(
        dates, train_end, valid_end, embargo_days
    )
    
    # 验证交易日序列：
    # dates[10] 是 train_end (index 10)
    # valid_start 应该在 dates[10 + 4] = dates[14]
    # dates[15] 是 valid_end (index 15)
    # test_start 应该在 dates[15 + 4] = dates[19]
    
    assert valid_start == dates[14], f"错误：验证集起始日错误，期待 {dates[14]}，实际 {valid_start}"
    assert test_start == dates[19], f"错误：测试集起始日错误，期待 {dates[19]}，实际 {test_start}"
    
    print("✅ 测试 3.3 顺利通过！")


def run_all_tests():
    print("======================================================================")
    print("🚀 开始执行第三阶段：Qlib风格算子、动态Handler与隔离带流水线单元测试")
    print("======================================================================")
    
    test_greater_less_operators()
    test_data_handler_compilation()
    test_embargo_safety_calculation()
    
    print("\n======================================================================")
    print("🎉 恭喜！第三阶段全部可插拔流水线设计与防泄露测试顺利通过！")
    print("======================================================================")


if __name__ == "__main__":
    run_all_tests()
