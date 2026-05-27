# -*- coding: utf-8 -*-
"""
DataPortal: Temporal Isolation Sandbox for High-Fidelity Quant Backtesting
DataPortal: 高保真量化回测的时序隔离沙箱数据网关

Provides strict data access control to enforce temporal safety, preventing strategies from 
querying future prices. Optimized via sorted DatetimeIndex slicing for high performance.
提供严格的数据访问控制以确保时序安全，防止策略查询未来价格。通过排序 DatetimeIndex 切片进行高性能优化。
"""
import pandas as pd


class DataPortal:
    """
    DataPortal manages the market price data feed inside the event-driven backtesting loop.
    It isolates data queries based on the simulated current timestamp to ensure look-ahead safety.
    DataPortal 在事件驱动回测循环内管理行情价格数据输入。
    它基于模拟的当前时间戳隔离数据查询，以确保防止未来函数泄露的安全。
    """

    def __init__(self, df: pd.DataFrame):
        """
        Initialize the DataPortal and pre-sort the DataFrame to ensure fast index-based binary search.
        初始化 DataPortal，并预先对 DataFrame 排序，以确保基于索引的二分极速查找。

        Parameters / 参数:
            df (pd.DataFrame): The raw market price panel dataset, with MultiIndex index level names ['date', 'ticker'].
                               原始行情面板数据，必须具有双重索引 ['date', 'ticker']。
        """
        # Ensure the index levels are correctly ordered and sorted
        # 确保索引层级按规范排列，并执行升序物理排序，这是 pandas 极速 O(log N) loc 切片检索的基础
        if not isinstance(df.index, pd.MultiIndex) or "date" not in df.index.names or "ticker" not in df.index.names:
            raise ValueError(
                "DataPortal requires a MultiIndex DataFrame with levels named ['date', 'ticker']."
                "DataPortal 要求输入的 DataFrame 必须具备 ['date', 'ticker'] 级别的 MultiIndex 索引。"
            )
        
        # Sort by first index level 'date' then 'ticker'
        # 按照双重索引物理升序排序
        self._raw_df = df.sort_index(level=["date", "ticker"])

    def get_history(self, ticker: str, field: str, current_date: pd.Timestamp, N: int) -> pd.Series:
        """
        Retrieve the latest N historical bars of a specific ticker up to and including the current date.
        Strictly truncates any dates strictly greater than current_date.
        检索指定 ticker 截至当前日期（含当前日期）的最新 N 期历史数据系列。
        物理切断任何严密大于当前日期的未来行。

        Parameters / 参数:
            ticker (str): Asset identifier (e.g. 'AAPL') / 资产代码。
            field (str): Column field to query (e.g. 'close') / 查询字段。
            current_date (pd.Timestamp): The current trading date of the backtest loop / 当前模拟交易日。
            N (int): Number of historical bars to retrieve / 历史长度 N。

        Returns / 返回:
            pd.Series: Historic series with a single DatetimeIndex / 带有单时间索引的历史时序。
        """
        # Slice the sorted MultiIndex extremely fast in O(log N) using the sorted datetime index boundary.
        # This completely avoids doing O(N) full boolean scan over index level values.
        # 使用已排序 MultiIndex 的极速 loc 时间切片，完全规避对全表执行 O(N) 级别的布尔条件线性扫描。
        time_truncated_df = self._raw_df.loc[:current_date]

        try:
            # xs extracts a sub-view for a particular ticker, dropping the ticker index level
            # xs 用以提取指定股票的子视图，并在结果中剥除该股票索引层
            ticker_series = time_truncated_df.xs(ticker, level="ticker")[field]
            return ticker_series.tail(N)
        except KeyError:
            # Return an empty series if the ticker doesn't exist on or before the current date
            # 如果该资产在当前日期或历史时期未上市或无有效数据，返回空的 float64 序列
            return pd.Series(dtype="float64")

    def get_current(self, ticker: str, field: str, current_date: pd.Timestamp) -> float:
        """
        Get the instantaneous current bar value of a field for a specific ticker.
        获取指定 ticker 在当前交易日特定字段的瞬时行情价格数值。

        Parameters / 参数:
            ticker (str): Asset identifier / 资产代码。
            field (str): Field column name / 查询字段。
            current_date (pd.Timestamp): Current trading date / 当前模拟交易日。

        Returns / 返回:
            float: The current value, or float('nan') if missing / 当前行情值，缺失则返回 nan。
        """
        try:
            # Performs O(log N) multi-key lookup in sorted MultiIndex via binary search
            # 执行已排序 MultiIndex 的 O(log N) 二分双键联合定位
            return float(self._raw_df.loc[(current_date, ticker), field])
        except KeyError:
            return float("nan")
