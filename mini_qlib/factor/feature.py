"""
================================================================================
                    MiniQLib Registry-based Feature Library
================================================================================

本文件实现了基于“注册制”的经典量化特征（因子）库。
涵盖了微软 Qlib 框架中经典的 Alpha158 核心因子子集：
包括 K线实体比例（KMID）、波动区间（KLEN）、影线特征（KUP/KLOW）、滚动均线偏离（MA）、
滚动动量（ROC）、滚动标准差（STD）、随机指标（RSV）等。
支持新手以“一键注册与按名索骥”的形式极速调用，直接作为配置链流水线的数据源，实现高度可插拔架构。
"""
from typing import Union, Dict, List
from mini_qlib.data.expression import Feature, MiniExpression
from mini_qlib.data.ops import Mean, Ref, Min, Max, Greater, Less


class FeatureRegistry:
    """
    特征注册表类 (Feature Registry Class)
    用于管理和存取经典的量化特征公式。
    """
    def __init__(self):
        self._registry: Dict[str, Union[str, MiniExpression]] = {}
        self._descriptions: Dict[str, str] = {}

    def register(self, name: str, expr: Union[str, MiniExpression], desc: str = "") -> None:
        """
        注册一个新特征 (Register a new feature)
        
        Parameters
        ----------
        name : str
            特征名称 (e.g., "KMID")
        expr : str | MiniExpression
            特征对应的公式字符串或预先装配好的 AST 表达式对象
        desc : str
            特征的业务含义描述
        """
        self._registry[name] = expr
        self._descriptions[name] = desc

    def get(self, name: str) -> Union[str, MiniExpression]:
        """获取已注册的特征表达式 (Get registered feature expression)"""
        if name not in self._registry:
            raise KeyError(
                f"❌ 特征注册表中未发现: '{name}'\n"
                f"   已注册的特征包括: {self.list_all()}"
            )
        return self._registry[name]

    def get_description(self, name: str) -> str:
        """获取特征业务描述 (Get feature description)"""
        return self._descriptions.get(name, "无描述说明")

    def list_all(self) -> List[str]:
        """列出所有已注册的特征键名 (List all registered feature names)"""
        return list(self._registry.keys())


# 创建全局唯一的特征注册表实例
feature_registry = FeatureRegistry()

# ──────────────────────────────────────────────────────────────────────────
#                注册经典 Alpha158 K线柱特征 (K-Bar Features)
# ──────────────────────────────────────────────────────────────────────────

# 1. 实体涨跌幅比例 (KMID)
# 对应 Qlib: ($close-$open)/$open
feature_registry.register(
    name="KMID",
    expr="($close-$open)/$open",
    desc="K线实体涨跌幅比例：当日收盘价与开盘价之差除以开盘价"
)

# 2. 全天振幅比率 (KLEN)
# 对应 Qlib: ($high-$low)/$open
feature_registry.register(
    name="KLEN",
    expr="($high-$low)/$open",
    desc="K线全天振幅比率：当日最高价与最低价之差除以开盘价"
)

# 3. 影线与实体比率 (KMID2)
feature_registry.register(
    name="KMID2",
    expr="($close-$open)/($high-$low+1e-12)",
    desc="影线实体比率：实体大小占全天波动幅度的比例"
)

# 4. 上影线长度占比 (KUP)
# 对应 Qlib: ($high-Greater($open,$close))/$open
feature_registry.register(
    name="KUP",
    expr="($high-Greater($open,$close))/$open",
    desc="上影线比例：最高价与实体上沿（开盘和收盘较大值）之差除以开盘价"
)

# 5. 下影线长度占比 (KLOW)
# 对应 Qlib: (Less($open,$close)-$low)/$open
feature_registry.register(
    name="KLOW",
    expr="(Less($open,$close)-$low)/$open",
    desc="下影线比例：实体下沿（开盘和收盘较小值）与最低价之差除以开盘价"
)

# 6. 收盘价偏离中枢 (KSFT)
feature_registry.register(
    name="KSFT",
    expr="(2*$close-$high-$low)/$open",
    desc="收盘价偏离中枢度：两倍收盘价偏离全天中枢的比率"
)


# ──────────────────────────────────────────────────────────────────────────
#                注册经典 Alpha158 时序滚动特征 (Rolling Features)
# ──────────────────────────────────────────────────────────────────────────

# 5日价格动量 (ROC5)
feature_registry.register(
    name="ROC5",
    expr="Ref($close,5)/$close",
    desc="5日价格动量：5天前的收盘价与今日收盘价的比率 (Qlib 标准除法形式)"
)

# 10日价格动量 (ROC10)
feature_registry.register(
    name="ROC10",
    expr="Ref($close,10)/$close",
    desc="10日价格动量：10天前的收盘价与今日收盘价的比率"
)

# 5日均线偏离度 (MA5)
feature_registry.register(
    name="MA5",
    expr="Mean($close,5)/$close-1",
    desc="5日移动平均偏离度：过去5日收盘均价相对今日收盘价的偏离比率"
)

# 10日均线偏离度 (MA10)
feature_registry.register(
    name="MA10",
    expr="Mean($close,10)/$close-1",
    desc="10日移动平均偏离度：过去10日收盘均价相对今日收盘价的偏离比率"
)

# 5日价格滚动标准差 (STD5)
feature_registry.register(
    name="STD5",
    expr="Std($close,5)/$close",
    desc="5日收盘价波动率：过去5日收盘价的标准差除以收盘价以消除单位量级"
)

# 10日成交量偏离度 (VMA10)
feature_registry.register(
    name="VMA10",
    expr="Mean($volume,10)/($volume+1e-12)-1",
    desc="10日成交量移动平均偏离度：过去10日平均成交量相对今日成交量的偏离"
)

# 5日 RSV 随机指标 (RSV5)
# 对应 Qlib: ($close-Min($low,5))/(Max($high,5)-Min($low,5)+1e-12)
feature_registry.register(
    name="RSV5",
    expr="($close-Min($low,5))/(Max($high,5)-Min($low,5)+1e-12)",
    desc="5日 RSV 随机指标：当前价格处于过去5天波动最高最低区间的相对百分比位置"
)


# ──────────────────────────────────────────────────────────────────────────
#                同时支持纯 AST 算子对象版本的极速获取
# ──────────────────────────────────────────────────────────────────────────
# 方便高级研究员直接采用原生计算图进行特征拓扑的快速搭建
close_f = Feature("close")
feature_registry.register(
    name="KMID_ast",
    expr=(close_f - Feature("open")) / Feature("open"),
    desc="实体涨跌幅比例 (纯 AST 算子对象版，可直接调用 .load(df) 计算)"
)
