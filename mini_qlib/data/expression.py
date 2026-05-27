"""
================================================================================
                    MiniExpression AST Core Foundation
================================================================================

                           MiniExpression (基类/地基)
                                  │
         ┌────────────────────────┴────────────────────────┐
         ▼                                                 ▼
   Feature (原子量价特征)                          [ Operator Overloading ]
    (e.g., "$close" -> "$")                       (重载 __add__, __sub__, 等)
         │                                                 │
         ▼                                                 ▼
   PFeature (时点财务特征)                         (动态编译并实例化位于 ops.py 的算子)
    (e.g., "$$revenue" -> "$$")                     (Sub, Add, Mean, Ref 等)
                                                           │
                                                           ▼
                                                递归生成全局唯一公式串与缓存键
                                                str(expr) -> "Sub(Mean($close,20),1)"

本文件包含 mini_qlib 算子引擎的底层 AST 计算树基类与原子特征类。
作为整个系统的地基，它与具体算子分离，以彻底规避循环导入风险。
"""
from __future__ import annotations

import pandas as pd
from typing import Optional, Dict, Any, Union, List, Tuple
import logging

_log = logging.getLogger(__name__)


class MiniExpression:
    """
    所有表达式、原子特征和计算算子的终极基类。
    
    【核心职责】：
    1. 【运算符重载】：重载 Python 的四则运算与比较运算符（__add__, __sub__, __gt__, 等），
       使得用户在编写表达式时，能通过 $close - $open 自动嵌套组装成一颗 AST（抽象语法树）计算图，
       而不需要手动通过各种类名去构建。
    2. 【缓存控制与生命周期】：统一暴露 `load()` 接口，作为数据加载和计算的唯一入口。
       在基类中拦截并处理缓存（以 __str__ 生成的唯一因子 ID 作为缓存键），避免因子的重复计算。
    3. 【计算协议规范】：规定子类必须实现的 `_load_internal()` 数据计算接口。
    4. 【时间窗口扩展机制】：声明 `get_extended_window_size()`，用来自动计算在特定日期区间内计算该因子
       所需要的叶子节点（基础特征）的额外历史/未来数据长度。
    """

    def __init__(self, *args, **kwargs):
        """
        所有算子的通用初始化。
        在这里自动记录所有的构造参数，用于缓存键的生成与无重复代码的序列化。
        """
        self.args = args
        self.kwargs = kwargs

    def load(self, df: pd.DataFrame, context: Optional[Dict[str, Any]] = None) -> pd.Series:
        """
        因子计算与加载的统一入口。
        Unified entry point for factor computation and loading.
        
        Parameters
        ----------
        df : pd.DataFrame
            输入的原始数据集，要求包含双重索引（datetime, ticker）或单重索引（datetime）。
            Input raw dataset, must contain a dual index (datetime, ticker) or single index (datetime).
        context : dict, optional
            缓存上下文，用于避免重复计算子表达式。
            Cache context dict used to avoid redundant sub-expression computation.
            
        Returns
        -------
        pd.Series
            计算完成的单因子序列，其 Index 必须与输入的 df 保持完全一致。
            Computed single factor series whose index must be exactly aligned with the input df.
        """
        if context is None:
            return self._load_internal(df)
            
        key = str(self)
        if key not in context:
            context[key] = self._load_internal(df, context=context)
        return context[key]

    def _load_internal(self, df: pd.DataFrame, context: Optional[Dict[str, Any]] = None) -> pd.Series:
        """
        具体的因子计算逻辑，由各个子类算子（如 Ref, Mean, Add）各自实现。
        Concrete factor computation logic, implemented by each subclass operator (e.g., Ref, Mean, Add).
        """
        raise NotImplementedError("每个具体的算子必须实现 _load_internal 方法！")

    def __str__(self) -> str:
        """
        全自动生成的因子唯一字符串 ID，作为缓存键和序列化的核心。
        子类若未覆盖本方法，则自动递归格式化所有子参数。
        """
        args_str = ",".join(str(arg) for arg in self.args)
        return f"{type(self).__name__}({args_str})"

    def __repr__(self) -> str:
        return str(self)

    # ==========================================================================
    #                  运算符重载：使用 Python 魔法方法自动构建 AST 树
    # ==========================================================================
    def __add__(self, other) -> 'MiniExpression':
        from .ops import Add
        return Add(self, other)

    def __radd__(self, other) -> 'MiniExpression':
        from .ops import Add
        return Add(other, self)

    def __sub__(self, other) -> 'MiniExpression':
        from .ops import Sub
        return Sub(self, other)

    def __rsub__(self, other) -> 'MiniExpression':
        from .ops import Sub
        return Sub(other, self)

    def __mul__(self, other) -> 'MiniExpression':
        from .ops import Mul
        return Mul(self, other)

    def __rmul__(self, other) -> 'MiniExpression':
        from .ops import Mul
        return Mul(other, self)

    def __truediv__(self, other) -> 'MiniExpression':
        from .ops import Div
        return Div(self, other)

    def __rtruediv__(self, other) -> 'MiniExpression':
        from .ops import Div
        return Div(other, self)

    def __gt__(self, other) -> 'MiniExpression':
        from .ops import Gt
        return Gt(self, other)

    def __ge__(self, other) -> 'MiniExpression':
        from .ops import Ge
        return Ge(self, other)

    def __lt__(self, other) -> 'MiniExpression':
        from .ops import Lt
        return Lt(self, other)

    def __le__(self, other) -> 'MiniExpression':
        from .ops import Le
        return Le(self, other)

    def __eq__(self, other) -> 'MiniExpression':
        from .ops import Eq
        return Eq(self, other)

    def __ne__(self, other) -> 'MiniExpression':
        from .ops import Ne
        return Ne(self, other)

    # ==========================================================================
    #                       时间窗口扩张协议 (Extended Window)
    # ==========================================================================
    def get_extended_window_size(self) -> Tuple[int, int]:
        """
        获取为了计算当前因子，在 [start, end] 区间内所需向左（过去）和向右（未来）扩展的窗口大小。
        """
        raise NotImplementedError()


class Feature(MiniExpression):
    """
    最底层的叶子节点：基础变量算子（静态变量加载）。
    代表数据库中直接存在的列，如 $close, $open, $volume。
    """
    def __init__(self, name: str):
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"${self.name}"

    def _load_internal(self, df: pd.DataFrame, context: Optional[Dict[str, Any]] = None) -> pd.Series:
        # 直接提取基础列
        if self.name in df.columns:
            return df[self.name]
        raise KeyError(f"数据集中未发现特征列: {self.name}")

    def get_extended_window_size(self) -> Tuple[int, int]:
        return 0, 0


class PFeature(Feature):
    """
    Point-in-Time 基础特征算子。
    __str__ 返回 "$$name"，用于处理带版本演进的财务数据。
    现在支持 context 缓存，避免同一 AST 中多次引用相同财务指标时的重复数据库查询。
    """
    def __str__(self) -> str:
        return f"$${self.name}"

    def _load_internal(self, df: pd.DataFrame, context: Optional[Dict[str, Any]] = None) -> pd.Series:
        # PFeature queries the edgar.duckdb database and performs Point-in-Time (PIT) alignment
        # using an O(N log N) ASOF merge in pandas, ensuring zero future look-ahead bias.
        # PFeature 查询 edgar.duckdb 数据库并执行 Point-in-Time (PIT) 对齐，
        # 使用 pandas 的 O(N log N) ASOF merge，确保零未来前瞻偏差。
        
        name = self.name.lower()
        
        # Check column mapping to target tables
        COLUMN_TO_TABLE = {
            "revenue": "income",
            "gross_profit": "income",
            "op_income": "income",
            "net_income": "income",
            "eps_diluted": "income",
            "total_assets": "balance",
            "total_liabilities": "balance",
            "equity": "balance",
            "cash": "balance",
            "total_debt": "balance",
            "cfo": "cashflow",
            "capex": "cashflow",
            "fcf_direct": "cashflow"
        }
        
        if name not in COLUMN_TO_TABLE:
            raise KeyError(
                f"❌ PIT基本面列 '{self.name}' 不在支持的字段列表中。\n"
                f"   可用字段包括: {list(COLUMN_TO_TABLE.keys())}"
            )
            
        table_name = COLUMN_TO_TABLE[name]
        
        # Open connection to default edgar.duckdb
        from mini_qlib.utils.config import get_db
        
        try:
            with get_db(read_only=True) as conn:
                query = f"SELECT ticker, filed, period_end, {name} FROM {table_name} ORDER BY ticker, filed"
                fund_df = conn.execute(query).df()
        except Exception as e:
            # Log the error so users can diagnose why factor values are NaN
            # 记录错误日志，方便用户排查为何因子结果全为 NaN
            _log.warning(
                "PFeature '%s' 数据库查询失败 (database query failed): %s. 返回全 NaN 序列。",
                self.name, e
            )
            return pd.Series(index=df.index, dtype="float64")
                
        if fund_df.empty:
            _log.info(
                "PFeature '%s' 查询结果为空 (no data in table '%s'), 返回全 NaN 序列。",
                self.name, table_name
            )
            return pd.Series(index=df.index, dtype="float64")
            
        # Parse dates to pandas Timestamp objects
        fund_df["filed"] = pd.to_datetime(fund_df["filed"])
        fund_df["period_end"] = pd.to_datetime(fund_df["period_end"])
        
        # Deduplicate revisions on same filed date: keep latest revision (max period_end)
        fund_df = fund_df.sort_values(by=["ticker", "filed", "period_end"])
        fund_df = fund_df.drop_duplicates(subset=["ticker", "filed"], keep="last")
        
        # Reset price DataFrame index to enable merge_asof on a single column
        prices = df.reset_index()
        # pandas requires date index to be strictly sorted for ASOF merge
        prices_sorted = prices.sort_values(by="date")
        
        # Align column names for merge_asof
        fund_df = fund_df.rename(columns={"filed": "date"})
        fund_sorted = fund_df[["ticker", "date", name]].sort_values(by="date")
        
        # Force identical datetime64[ns] dtype to prevent ASOF merge errors in pandas 2.0+
        prices_sorted["date"] = prices_sorted["date"].astype("datetime64[ns]")
        fund_sorted["date"] = fund_sorted["date"].astype("datetime64[ns]")
        
        # Perform highly optimized ASOF merge
        # 'backward' matches latest filing on or before the price date for each ticker
        merged = pd.merge_asof(
            prices_sorted,
            fund_sorted,
            on="date",
            by="ticker",
            direction="backward"
        )
        
        # Restore index and reorder to match input df
        merged = merged.set_index(["date", "ticker"]).sort_index()
        result_series = merged[name].reindex(df.index)
        return result_series
