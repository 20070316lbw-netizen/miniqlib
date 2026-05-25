import pandas as pd
import numpy as np

def make_label(df: pd.DataFrame,
               n_periods: int = 5,
               price_col: str = "close",
               gap: int = 1,
               ) -> pd.Series:
    """
    Args:
        df: 含有 date, ticker, price_col 的普通 DataFrame
            (date、ticker 是普通列,不是 index)
        n_periods: 持仓天数 (预测未来多少天的累计收益)
        price_col: 用哪列价 (默认 close)
        gap: 当前 t 和进场之间隔几期 (默认 1, 即 t+1 开仓, t+1+N 平仓)
    Returns:
        Series, 与输入 df 行对齐, 值是未来 N 日收益率
        (NaN 会出现在每只股票末尾的 gap + n_periods 行,因为未来数据不存在)
    """
    # 先按 ticker 和 date 排序,保证 shift 的方向正确
    # 不排序的话,如果 df 是乱序的,shift 出来的"未来"可能是别的日期
    df = df.sort_values(['ticker', 'date'])

    # 按 ticker 分组对 price_col 做 shift
    # 这里用列名 'ticker' 而不是 level=,跟 make_features.py 保持接口一致
    by_inst = df.groupby('ticker')[price_col]

    # shift(-k) 表示把 k 期之后的值挪到当前行
    #   enter:  t + gap 时刻的价格(进场价)
    #   exit_:  t + gap + n_periods 时刻的价格(平仓价)
    enter = by_inst.shift(-gap)
    exit_ = by_inst.shift(-(gap + n_periods))

    return (exit_ / enter - 1).rename(f"label_{n_periods}d")
