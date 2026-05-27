"""
================================================================================
                    MiniQlib Operators Collection Engine
================================================================================

                          MiniExpression (AST Core)
                                     │
                                     ▼
                        ExpressionOps (参数与属性捕获中心)
                                     │
        ┌───────────────────┬────────┴───────────┬───────────────────┐
        │ [__init_subclass__] 类定义时自动拦截     │                   │
        │ [_params_locked]  叶子节点参数加锁       │                   │
        ▼                                        ▼                   ▼
  ElemOperator                             PairOperator         If 算子
 (单目元素算子)                            (双目配对算子)       (三目选择算子)
  (e.g., Abs, Sign, Log)                     │                If(cond, L, R)
                                             ▼
                                       NpPairOperator
                                  (Add, Sub, Mul, Div, Gt)
                                             │
                                             ▼
                                          Rolling
                                       (滚动窗口算子)
                                  (Ref, Mean, Sum, Max, Min)
                                    (类级 _func = "mean")

本文件为 mini_qlib 算子的具体收集与设计蓝图。
已将 MiniExpression, Feature, PFeature 剥离至 expression.py。
本文件专注于各种算子的动态继承、参数捕获与计算设计。
"""
import numpy as np
import pandas as pd
import inspect
import re
from typing import Union, List, Tuple

# 从底层 AST 地基中引入核心类型，规避循环依赖
from .expression import MiniExpression, Feature, PFeature


# ##############################################################################
# ###################### 1. 动态算子基类: ExpressionOps ########################
# ##############################################################################
class ExpressionOps(MiniExpression):
    """
    算子基类：ExpressionOps (参数与属性自动捕获中心)
    
    【核心设计：彻底告别重复代码与硬编码】
    本类利用 Python 的 `__init_subclass__` 类钩子与 `inspect.signature` 反射机制，
    在子类实例化时全自动实现属性解析与绑定，并内置“参数锁（_params_locked）”机制防范多层继承覆盖。
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        # 只在子类自身定义了 __init__ 时进行拦截包装；若未定义，则自动继承父类已包裹的 __init__
        if "__init__" in cls.__dict__:
            original_init = cls.__init__
            sig = inspect.signature(original_init)
            params = [p for p in sig.parameters if p != 'self']
            
            def wrapped_init(self, *args, **kwargs):
                # 只有当最外层子类的第一次调用时（即锁未被占用时），才解析并绑定属性
                is_root_call = not hasattr(self, '_params_locked')
                if is_root_call:
                    self._params_names = params
                    self._params_values = args
                    self._params_locked = True  # 锁住参数，防止父类的包装器在此后的继承调用链中再次覆盖
                    
                    # 动态反射绑定形参值到 self 属性，并装填 self.args
                    bound = sig.bind(self, *args, **kwargs)
                    bound.apply_defaults()
                    self.args = []
                    for name, value in bound.arguments.items():
                        if name != 'self':
                            param = sig.parameters[name]
                            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                                setattr(self, name, value)
                                self.args.extend(value)  # 扁平化追加，而非 meta-tuple
                            else:
                                setattr(self, name, value)
                                self.args.append(value)
                else:
                    # 非根节点（父类构造）调用时，依然需要绑定父类自身的特有属性（如 self.func），但绝不能修改 self.args
                    bound = sig.bind(self, *args, **kwargs)
                    bound.apply_defaults()
                    for name, value in bound.arguments.items():
                        if name != 'self':
                            setattr(self, name, value)
                
                # 执行子类原始的 __init__ 构造逻辑 (如做参数校验等)
                original_init(self, *args, **kwargs)
                        
            cls.__init__ = wrapped_init

    # 基类默认构造，供无需自定义 __init__ 且无父层构造的极致精简子类直接继承使用
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def get_longest_back_rolling(self) -> int:
        """
        自动追溯子树中所有依赖因子的最长回溯长度。
        """
        # 如果是叶子节点或单因子算子，穿透调用
        if hasattr(self, "feature"):
            return self.feature.get_longest_back_rolling()
        # 如果是双因子算子，取最大值
        left_br = self.feature_left.get_longest_back_rolling() if isinstance(self.feature_left, MiniExpression) else 0
        right_br = self.feature_right.get_longest_back_rolling() if isinstance(self.feature_right, MiniExpression) else 0
        return max(left_br, right_br)


# ##############################################################################
# #################### 2. 算子族群分类规划 (Operator Families) ####################
# ##############################################################################

# ==============================================================================
# 2.1 单目元素算子 (Element-Wise Operators)
# ==============================================================================
class ElemOperator(ExpressionOps):
    """
    单目元素级计算算子的基类。
    特征：只接收一个子因子 `feature`。
    """
    def __init__(self, feature: MiniExpression):
        # 拦截包装器会自动绑定 self.feature = feature，这里无需代码
        pass

    def get_extended_window_size(self) -> Tuple[int, int]:
        return self.feature.get_extended_window_size()


class Abs(ElemOperator):
    """
    绝对值算子：Abs($close)
    """
    def _load_internal(self, df: pd.DataFrame, context: dict = None) -> pd.Series:
        series = self.feature.load(df, context=context)
        return series.abs()


class Log(ElemOperator):
    """
    对数算子：Log($close)
    """
    def _load_internal(self, df: pd.DataFrame, context: dict = None) -> pd.Series:
        series = self.feature.load(df, context=context)
        return np.log(series)


class Sign(ElemOperator):
    """
    符号算子：Sign($close)
    """
    def _load_internal(self, df: pd.DataFrame, context: dict = None) -> pd.Series:
        series = self.feature.load(df, context=context)
        return np.sign(series)


# ==============================================================================
# 2.2 双目配对算子 (Pair-Wise Operators)
# ==============================================================================
class PairOperator(ExpressionOps):
    """
    双目配对计算算子的基类。
    特征：接收 `feature_left` 和 `feature_right` 两个输入（可以是子因子，也可以是常数）。
    """
    def __init__(self, feature_left: Union[MiniExpression, float, int], 
                 feature_right: Union[MiniExpression, float, int]):
        # 拦截包装器会自动绑定 self.feature_left = feature_left, self.feature_right = feature_right
        pass

    def get_extended_window_size(self) -> Tuple[int, int]:
        left_window = self.feature_left.get_extended_window_size() if isinstance(self.feature_left, MiniExpression) else (0, 0)
        right_window = self.feature_right.get_extended_window_size() if isinstance(self.feature_right, MiniExpression) else (0, 0)
        return max(left_window[0], right_window[0]), max(left_window[1], right_window[1])


class NpPairOperator(PairOperator):
    """
    基于 Numpy 的双目配对计算算子基类。
    """
    def __init__(self, feature_left: Union[MiniExpression, float, int], 
                 feature_right: Union[MiniExpression, float, int], 
                 func: str):
        # 拦截包装器会自动绑定 self.feature_left, self.feature_right, self.func
        pass

    def _load_internal(self, df: pd.DataFrame, context: dict = None) -> pd.Series:
        series_left = self.feature_left.load(df, context=context) if isinstance(self.feature_left, MiniExpression) else self.feature_left
        series_right = self.feature_right.load(df, context=context) if isinstance(self.feature_right, MiniExpression) else self.feature_right
        
        # 提取底层的 Numpy 计算函数（如 add, subtract, multiply, divide, greater 等）
        calc_func = getattr(np, self.func)
        res = calc_func(series_left, series_right)
        
        # 保持 Series 形式输出
        if isinstance(res, (pd.Series, np.ndarray)):
            # 兼容左侧/右侧是 pd.Series 的 index
            ref_index = series_left.index if isinstance(series_left, pd.Series) else series_right.index
            return pd.Series(res, index=ref_index)
        return res


class Add(NpPairOperator):
    """加法算子：$close + $open"""
    def __init__(self, feature_left, feature_right):
        super().__init__(feature_left, feature_right, "add")


class Sub(NpPairOperator):
    """减法算子：$close - $open"""
    def __init__(self, feature_left, feature_right):
        super().__init__(feature_left, feature_right, "subtract")


class Mul(NpPairOperator):
    """乘法算子：$close * $open"""
    def __init__(self, feature_left, feature_right):
        super().__init__(feature_left, feature_right, "multiply")


class Div(NpPairOperator):
    """除法算子：$close / $open"""
    def __init__(self, feature_left, feature_right):
        super().__init__(feature_left, feature_right, "divide")


class Gt(NpPairOperator):
    """大于算子：$close > $open"""
    def __init__(self, feature_left, feature_right):
        super().__init__(feature_left, feature_right, "greater")


class Ge(NpPairOperator):
    """大于等于：$close >= $open"""
    def __init__(self, feature_left, feature_right):
        super().__init__(feature_left, feature_right, "greater_equal")


class Lt(NpPairOperator):
    """小于：$close < $open"""
    def __init__(self, feature_left, feature_right):
        super().__init__(feature_left, feature_right, "less")


class Le(NpPairOperator):
    """小于等于：$close <= $open"""
    def __init__(self, feature_left, feature_right):
        super().__init__(feature_left, feature_right, "less_equal")


class Eq(NpPairOperator):
    """等于：$close == $open"""
    def __init__(self, feature_left, feature_right):
        super().__init__(feature_left, feature_right, "equal")


class Ne(NpPairOperator):
    """不等于：$close != $open"""
    def __init__(self, feature_left, feature_right):
        super().__init__(feature_left, feature_right, "not_equal")


class Greater(NpPairOperator):
    """元素级较大值算子：Greater($open, $close)"""
    def __init__(self, feature_left, feature_right):
        super().__init__(feature_left, feature_right, "maximum")


class Less(NpPairOperator):
    """元素级较小值算子：Less($open, $close)"""
    def __init__(self, feature_left, feature_right):
        super().__init__(feature_left, feature_right, "minimum")


# ==============================================================================
# 2.3 三目条件算子 (Triple-Wise Operators)
# ==============================================================================
class If(ExpressionOps):
    """
    条件选择算子：If(condition, feature_left, feature_right)
    当 condition 满足时返回 left，否则返回 right。
    """
    def __init__(self, condition: MiniExpression, 
                 feature_left: Union[MiniExpression, float, int], 
                 feature_right: Union[MiniExpression, float, int]):
        pass

    def _load_internal(self, df: pd.DataFrame, context: dict = None) -> pd.Series:
        cond_series = self.condition.load(df, context=context)
        left_series = self.feature_left.load(df, context=context) if isinstance(self.feature_left, MiniExpression) else self.feature_left
        right_series = self.feature_right.load(df, context=context) if isinstance(self.feature_right, MiniExpression) else self.feature_right
        
        res = np.where(cond_series, left_series, right_series)
        return pd.Series(res, index=cond_series.index)

    def get_extended_window_size(self) -> Tuple[int, int]:
        c_window = self.condition.get_extended_window_size()
        left_window = self.feature_left.get_extended_window_size() if isinstance(self.feature_left, MiniExpression) else (0, 0)
        right_window = self.feature_right.get_extended_window_size() if isinstance(self.feature_right, MiniExpression) else (0, 0)
        return max(c_window[0], left_window[0], right_window[0]), max(c_window[1], left_window[1], right_window[1])


# ==============================================================================
# 2.4 滚动时间窗口算子 (Rolling / Expanding Window Operators)
# ==============================================================================
class Rolling(ExpressionOps):
    """
    滚动时间窗口算子的抽象基类。
    所有依赖历史时间窗口计算的算子（如 Ref, Mean, Sum 等）都属于这一族。
    Abstract base class for rolling time window operators.
    All operators relying on historical window computations (e.g., Ref, Mean, Sum) belong to this family.
    
    【高阶无硬编码设计】：
    - 各个子类（如 Mean）只需在类级别声明 `_func = "mean"`，不需要在 `__init__` 中硬编码传参！
    - 基类 `Rolling` 构造器通过 `self._func` 自动反射完成底层计算方法绑定。
    [High-Level No-Hardcoding Design]:
    - Each subclass (e.g., Mean) only needs to declare `_func = "mean"` at the class level, eliminating hardcoded constructor arguments!
    - The base `Rolling` constructor automatically binds underlying calculation methods via dynamic reflection of `self._func`.
    """
    
    _func = None

    def __init__(self, feature: MiniExpression, N: int, min_periods: int = 1):
        """
        Parameters
        ----------
        feature : MiniExpression
            输入的子表达式 (Input subexpression)
        N : int
            滚动窗口大小 (Rolling window size)
        min_periods : int, default 1
            滚动窗口计算所需的最小有效观测数 (Minimum number of observations in window required to have a value)
        """
        # 拦截包装器会自动绑定 self.feature = feature, self.N = N, self.min_periods = min_periods
        # The interceptor will automatically bind self.feature, self.N, and self.min_periods
        pass

    def __str__(self) -> str:
        """
        根据 min_periods 是否为默认值 1，动态生成最简公式字符串。
        Dynamically generate the simplified formula string based on whether min_periods is the default 1.
        """
        if hasattr(self, 'min_periods') and self.min_periods != 1:
            return f"{type(self).__name__}({self.feature},{self.N},{self.min_periods})"
        return f"{type(self).__name__}({self.feature},{self.N})"

    def _load_internal(self, df: pd.DataFrame, context: dict = None) -> pd.Series:
        series = self.feature.load(df, context=context)
        if isinstance(series.index, pd.MultiIndex) and 'ticker' in series.index.names:
            # groupby ticker 并进行 rolling 计算，然后用 droplevel 和 reorder_levels 还原索引与排序
            # groupby ticker and perform rolling calculation, then restore index names and ordering via droplevel and reorder_levels
            res = getattr(series.groupby(level='ticker').rolling(self.N, min_periods=self.min_periods), self._func)()
            res = res.droplevel(0)
            return res.reorder_levels(series.index.names).sort_index()
        else:
            return getattr(series.rolling(self.N, min_periods=self.min_periods), self._func)()

    def get_extended_window_size(self) -> Tuple[int, int]:
        lft_etd, rght_etd = self.feature.get_extended_window_size()
        if self.N > 0:
            lft_etd = max(lft_etd + self.N - 1, lft_etd)
        return lft_etd, rght_etd


class Ref(Rolling):
    """
    历史引用算子：Ref($close, 5) 代表 5 天前的收盘价。
    由于 shift 计算不是 pandas 内置的通用 rolling 统计指标，它独立处理。
    """
    def _load_internal(self, df: pd.DataFrame, context: dict = None) -> pd.Series:
        series = self.feature.load(df, context=context)
        if isinstance(series.index, pd.MultiIndex) and 'ticker' in series.index.names:
            res = series.groupby(level='ticker').shift(self.N)
            return res.reorder_levels(series.index.names).sort_index()
        return series.shift(self.N)

    def get_extended_window_size(self) -> Tuple[int, int]:
        lft_etd, rght_etd = self.feature.get_extended_window_size()
        if self.N > 0:
            lft_etd = max(lft_etd + self.N, lft_etd)
        elif self.N < 0:
            rght_etd = max(rght_etd - self.N, rght_etd)
        return lft_etd, rght_etd


class Mean(Rolling):
    """滚动均值算子 (移动平均线 MA)"""
    _func = "mean"


class Sum(Rolling):
    """滚动求和算子"""
    _func = "sum"


class Std(Rolling):
    """滚动标准差算子"""
    _func = "std"


class Max(Rolling):
    """滚动最大值算子"""
    _func = "max"


class Min(Rolling):
    """滚动最小值算子"""
    _func = "min"


# ==============================================================================
# 3. 因子引擎表达式解析器策划 (Formula Parser Design)
# ==============================================================================
def parse_field(field: str) -> str:
    """
    【架构解析核心函数】
    将用户输入的公式字符串，转换为等价的 Python 表达式代码字串。
    
    例如：
    "$close" -> "Feature('close')"
    "$$roewa_q" -> "PFeature('roewa_q')"
    "Ref($close, 1) > 0" -> "Ref(Feature('close'), 1) > 0"
    """
    if not isinstance(field, str):
        field = str(field)
    
    chinese_punctuation_regex = r"\u3001\uff1a\uff08\uff09"
    # 替换 $$[name] -> PFeature('[name]')
    field = re.sub(rf"\$\$([\w{chinese_punctuation_regex}]+)", r'PFeature("\1")', field)
    # 替换 $[name] -> Feature('[name]')
    field = re.sub(rf"\$([\w{chinese_punctuation_regex}]+)", r'Feature("\1")', field)
    
    return field


def get_op_namespace() -> dict:
    """
    获取包含所有特征和算子类名在内的计算名字空间，专门供 eval() 使用。
    Get the evaluation namespace containing all operators and features, designed for eval().
    """
    return {
        "Feature": Feature,
        "PFeature": PFeature,
        "Abs": Abs,
        "Log": Log,
        "Sign": Sign,
        "Add": Add,
        "Sub": Sub,
        "Mul": Mul,
        "Div": Div,
        "Gt": Gt,
        "Ge": Ge,
        "Lt": Lt,
        "Le": Le,
        "Eq": Eq,
        "Ne": Ne,
        "Greater": Greater,
        "Less": Less,
        "If": If,
        "Ref": Ref,
        "Mean": Mean,
        "Sum": Sum,
        "Std": Std,
        "Max": Max,
        "Min": Min,
    }
