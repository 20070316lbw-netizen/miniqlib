"""
================================================================================
                    MiniQLib Dynamic DataHandler Compiler
================================================================================

本文件实现了动态数据处理器 `DataHandler`。
它是配置驱动因子的核心编译器与数据结算底座：
1. 动态加载：能够解析配置字典，自动对接“注册制特征库”和“注册制标签库”；
2. 动态编译：支持普通公式字符串（如 "Mean($close, 10)/$close"），利用 parse_field 和 eval 全自动在内存编译为 AST 计算图；
3. 极速计算：统一调度 setup()，底层透传 context 缓存，消除算子子树重复计算；
4. 格式输出：将所有的特征和标签整合成带有完整 MultiIndex (date, ticker) 的最终训练 DataFrame。
"""
import pandas as pd
from typing import Dict, Union, Any, List
from mini_qlib.data.expression import MiniExpression
from mini_qlib.data.ops import parse_field, get_op_namespace
from mini_qlib.factor import label_registry, feature_registry


class DataHandler:
    """
    动态数据处理器 (Dynamic DataHandler)
    负责装配特征与标签的计算拓扑，并执行高性能的数据生产。
    """
    def __init__(self, df: pd.DataFrame, config: dict):
        """
        Parameters
        ----------
        df : pd.DataFrame
            包含原始行情基础数据（如 close, open, high, low, volume 等）的 DataFrame
        config : dict
            配置字典，格式通常为：
            {
                "features": {
                    "feature_name_1": "KMID",                 # 注册库中名字
                    "feature_name_2": "Mean($close,5)/$close", # 自定义表达式字符串
                    "feature_name_3": some_ast_object          # 预构建的 AST 对象
                },
                "labels": {
                    "label_name": "label_5d"
                }
            }
        """
        self.df = df
        self.config = config
        self.features: Dict[str, MiniExpression] = {}
        self.labels: Dict[str, MiniExpression] = {}
        
        # 一步到位，全自动编译
        self._compile()

    def _compile(self) -> None:
        """
        解析配置并进行 AST 语法树动态编译
        """
        op_ns = get_op_namespace()
        
        # 1. 编译所有特征 (Compile Features)
        feature_configs = self.config.get("features", {})
        for name, expr in feature_configs.items():
            self.features[name] = self._compile_single(expr, feature_registry, op_ns)

        # 2. 编译所有标签 (Compile Labels)
        label_configs = self.config.get("labels", {})
        for name, expr in label_configs.items():
            self.labels[name] = self._compile_single(expr, label_registry, op_ns)

    def _compile_single(self, expr: Any, registry: Any, op_ns: dict) -> MiniExpression:
        """
        编译单个表达式的递归处理机。
        支持：预构建 AST、注册中心名字检索、以及自定义公式文本解析。
        """
        # A. 如果本身就是已经预构建好的 AST 对象，直接通过
        if isinstance(expr, MiniExpression):
            return expr
        
        # B. 如果是字符串，首先判定是否为注册库的 Key；如果不是，则按原生文本编译
        if isinstance(expr, str):
            try:
                # 尝试从注册表获取
                registered_expr = registry.get(expr)
                # 递归编译（防止注册表里也是字符串公式，实现完美兼容）
                return self._compile_single(registered_expr, registry, op_ns)
            except KeyError:
                # 不在注册表中，启动编译器将 $ / $$ 替换为 Python 代码
                parsed_code = parse_field(expr)
                try:
                    # eval 编译，将字符串实例化为 AST 树，并禁用 __builtins__ 以防止任何恶意代码注入
                    # eval compilation, instantiating the string as an AST tree, and disabling __builtins__ to prevent any malicious code injection
                    ast_obj = eval(parsed_code, {"__builtins__": {}}, op_ns)
                    if not isinstance(ast_obj, MiniExpression):
                        raise ValueError(
                            f"公式 '{expr}' 编译结果类型不是 MiniExpression, 实际为: {type(ast_obj)}"
                        )
                    return ast_obj
                except Exception as e:
                    raise ValueError(
                        f"❌ 因子公式编译失败！\n"
                        f"   原始公式: '{expr}'\n"
                        f"   转换代码: '{parsed_code}'\n"
                        f"   错误信息: {e}"
                    )
        
        raise TypeError(f"不支持的因子描述类型 {type(expr)}: {expr}")

    def setup(self, context: dict = None) -> pd.DataFrame:
        """
        执行因子与标签的高性能结算计算。
        
        Parameters
        ----------
        context : dict, optional
            全局缓存上下文，共享给所有计算子树，防止任何重复算子的二次运算。
            
        Returns
        -------
        pd.DataFrame
            整合了所有计算后特征与标签的 DataFrame，索引 index 结构与输入的行情 df 保持一致。
        """
        if context is None:
            context = {}
            
        columns = {}
        
        # 1. 依次执行特征计算并放入暂存区 (Compute Features)
        for name, ast_expr in self.features.items():
            columns[name] = ast_expr.load(self.df, context=context)
            
        # 2. 依次执行标签计算并放入暂存区 (Compute Labels)
        for name, ast_expr in self.labels.items():
            columns[name] = ast_expr.load(self.df, context=context)
            
        # 3. 横向合并 (Concatenate columns)
        # pd.concat 能够以极高效率基于原 index 自动进行行对齐
        result_df = pd.concat(columns, axis=1)
        return result_df
