"""
================================================================================
                    MiniQLib Registry-based Label Library
================================================================================

本文件实现了基于“注册制”的经典量化预测标签库。
通过提供统一的注册接口，将各种预测周期（1日、5日、20日等）且带有进场时延（gap）的未来收益率公式集中管理，
支持新手以“字符串公式”或“预构建 AST 算子对象”的形式一键获取并灵活拔插，降低使用门槛。
"""
import pandas as pd
from typing import Union, Dict, List
from mini_qlib.data.expression import Feature, MiniExpression
from mini_qlib.data.ops import Ref


class LabelRegistry:
    """
    标签注册表类 (Label Registry Class)
    用于管理和存取各类标准因子标签。
    """
    def __init__(self):
        self._registry: Dict[str, Union[str, MiniExpression]] = {}
        self._descriptions: Dict[str, str] = {}

    def register(self, name: str, expr: Union[str, MiniExpression], desc: str = "") -> None:
        """
        注册一个新标签 (Register a new label)
        
        Parameters
        ----------
        name : str
            标签的唯一标识名称 (e.g., "label_5d")
        expr : str | MiniExpression
            标签对应的公式字符串或预先装配好的 AST 表达式对象
        desc : str
            该标签的简要业务含义说明
        """
        self._registry[name] = expr
        self._descriptions[name] = desc

    def get(self, name: str) -> Union[str, MiniExpression]:
        """获取已注册的标签表达式 (Get registered label expression)"""
        if name not in self._registry:
            raise KeyError(
                f"❌ 标签注册表中未发现: '{name}'\n"
                f"   已注册的标签包括: {self.list_all()}"
            )
        return self._registry[name]

    def get_description(self, name: str) -> str:
        """获取标签业务说明描述 (Get label business description)"""
        return self._descriptions.get(name, "无描述说明")

    def list_all(self) -> List[str]:
        """列出所有已注册的标签键名 (List all registered label names)"""
        return list(self._registry.keys())


# 创建全局唯一的标签注册表实例
label_registry = LabelRegistry()

# ──────────────────────────────────────────────────────────────────────────
#                注册经典的量化标签 (Standard Quant Labels)
# ──────────────────────────────────────────────────────────────────────────

# 1. 未来 1 日收益率 (1-Day Forward Return with 1-period gap for trade execution)
# 对应 Qlib: Ref($close, -2) / Ref($close, -1) - 1 (t+1 日开盘买入，t+2 日收盘卖出)
label_registry.register(
    name="label_1d",
    expr="Ref($close, -2) / Ref($close, -1) - 1",
    desc="未来 1 日收益率 (t+1日买入至t+2日卖出，避开当日 t=0 无法交易的问题)"
)

# 2. 未来 5 日收益率 (5-Day Forward Return with 1-period gap)
# 对应 Qlib: Ref($close, -6) / Ref($close, -1) - 1
label_registry.register(
    name="label_5d",
    expr="Ref($close, -6) / Ref($close, -1) - 1",
    desc="未来 5 日收益率 (t+1日开仓，持仓 5 天，t+6日平仓)"
)

# 3. 未来 10 日收益率 (10-Day Forward Return with 1-period gap)
# 对应 Qlib: Ref($close, -11) / Ref($close, -1) - 1
label_registry.register(
    name="label_10d",
    expr="Ref($close, -11) / Ref($close, -1) - 1",
    desc="未来 10 日收益率 (t+1日开仓，持仓 10 天，t+11日平仓)"
)

# 4. 未来 20 日收益率 (20-Day Forward Return with 1-period gap)
# 对应 Qlib: Ref($close, -21) / Ref($close, -1) - 1
label_registry.register(
    name="label_20d",
    expr="Ref($close, -21) / Ref($close, -1) - 1",
    desc="未来 20 日收益率 (t+1日开仓，持仓 20 天，t+21日平仓)"
)


# ──────────────────────────────────────────────────────────────────────────
#                同时支持纯 AST 算子对象版本的极速获取
# ──────────────────────────────────────────────────────────────────────────
# 新手也可以直接导入 AST 对象进行原生计算图操作，展示我们 AST 算子的高超对接能力
close_f = Feature("close")
label_registry.register(
    name="label_5d_ast",
    expr=Ref(close_f, -6) / Ref(close_f, -1) - 1,
    desc="未来 5 日收益率 (纯 AST 算子对象版，可直接调用 .load(df) 计算)"
)
