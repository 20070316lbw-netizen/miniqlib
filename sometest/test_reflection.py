"""
================================================================================
                    MiniQlib Phase 1 Unit Test Harness
================================================================================

                                 [ test_reflection.py ]
                                           │
         ┌───────────────────┬─────────────┼─────────────────────┐
         ▼                   ▼             ▼                     ▼
     [ 测试 1 ]          [ 测试 2 ]    [ 测试 3 ]            [ 测试 4 ]
    基础属性绑定         AST 树重载组装   多级继承参数锁          公式编译器 eval
   Mean($close, 20)      $close - $open   Add / Mean 嵌套锁      Mean($close,20)
         │                   │             │                     │
         ▼                   ▼             ▼                     ▼
     - feature=close     - Sub 节点根    - volume 绑定正常      - parse_field 正则
     - N=20              - Mean 左树     - add_op.args 隔离    - eval() 动态编译
     - args打包正常       - Ref 右树     - _params_locked 锁死  - 生成 Sub 树对象
         │                   │             │                     │
         └───────────────────┼─────────────┴─────────────────────┘
                             ▼
                    [ Assertions Checked ]
                             ▼
                       🎉 ALL PASSED!

sometest/test_reflection.py
用于第一阶段：ExpressionOps 动态参数捕获、防覆盖参数锁、以及运算符重载 AST 拓扑结构构建的单元测试脚本。
"""
import sys
from pathlib import Path

# 确保在 Windows 控制台下能够正确打印 UTF-8 编码的 Emoji 和中文
try:
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, OSError):
    pass

# 将项目根目录添加到 Python 路径中，以便能够干净地导入 mini_qlib
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 导入底层核心与具体算子
from mini_qlib.data.expression import Feature, PFeature, MiniExpression
from mini_qlib.data.ops import Mean, Ref, Add, Sub, Gt, parse_field


def run_tests():
    print("======================================================================")
    print("🚀 开始执行第一阶段：ExpressionOps 动态反射与参数锁单元测试")
    print("======================================================================")

    # ──────────────────────────────────────────────────────────────────────────
    # 测试 1: 基础算子的动态参数捕获与属性绑定
    # ──────────────────────────────────────────────────────────────────────────
    print("👉 测试 1: 基础算子的动态参数捕获与属性绑定...")
    
    close_feature = Feature("close")
    mean_op = Mean(close_feature, 20)

    # 1. 验证动态捕获的属性是否存在且正确
    assert hasattr(mean_op, "feature"), "错误：Mean 实例上没有自动生成 self.feature 属性！"
    assert hasattr(mean_op, "N"), "错误：Mean 实例上没有自动生成 self.N 属性！"
    
    assert mean_op.feature is close_feature, f"错误：self.feature 绑定值错误，期待 {close_feature}，实际 {mean_op.feature}"
    assert mean_op.N == 20, f"错误：self.N 绑定值错误，期待 20，实际 {mean_op.N}"
    
    # 2. 验证 args 自动打包
    assert hasattr(mean_op, "args"), "错误：算子实例上没有生成 self.args！"
    assert list(mean_op.args) == [close_feature, 20, 1], f"错误：self.args 打包参数错误，实际为 {mean_op.args}"

    # 3. 验证无硬编码序列化公式字符串
    assert str(mean_op) == "Mean($close,20)", f"错误：公式序列化错误，实际为: {str(mean_op)}"
    print("✅ 测试 1 顺利通过！")


    # ──────────────────────────────────────────────────────────────────────────
    # 测试 2: 运算符重载自动构建复杂的 AST 拓扑图
    # ──────────────────────────────────────────────────────────────────────────
    print("\n👉 测试 2: 运算符重载自动构建复杂的 AST 拓扑图...")
    
    close_f = Feature("close")
    open_f = Feature("open")
    
    # 构建表达式：Mean($close, 20) - Ref($open, 1)
    expr = Mean(close_f, 20) - Ref(open_f, 1)

    # 1. 验证类型
    assert isinstance(expr, Sub), f"错误：表达式树根节点应为 Sub 算子，实际为: {type(expr)}"
    
    # 2. 验证左树与右树属性全自动捕获
    assert expr.feature_left.feature is close_f, "错误：左树 Feature 绑定丢失"
    assert expr.feature_left.N == 20, "错误：左树时间窗口 N 绑定丢失"
    
    assert expr.feature_right.feature is open_f, "错误：右树 Feature 绑定丢失"
    assert expr.feature_right.N == 1, "错误：右树时间窗口 N 绑定丢失"

    # 3. 验证整棵 AST 树的一键递归序列化公式生成
    expected_formula = "Sub(Mean($close,20),Ref($open,1))"
    assert str(expr) == expected_formula, f"错误：整树序列化错误，期待 {expected_formula}，实际为 {str(expr)}"
    print("✅ 测试 2 顺利通过！")


    # ──────────────────────────────────────────────────────────────────────────
    # 测试 3: 多级继承链下的参数锁防覆盖测试
    # ──────────────────────────────────────────────────────────────────────────
    print("\n👉 测试 3: 多级继承链下的参数锁防覆盖测试...")
    
    # Mean(Rolling) -> Rolling(ExpressionOps) -> ExpressionOps
    # Rolling 拥有特征绑定，但 Mean 只定义了 _func = "mean"，无任何 __init__ 构造。
    # 实例化时会触发 Rolling 的包装拦截器。
    mean_op_2 = Mean(Feature("volume"), 10)
    
    assert mean_op_2.feature.name == "volume", "错误：多级继承下叶子参数绑定失败！"
    assert mean_op_2.N == 10, "错误：多级继承下窗口参数 N 绑定失败！"
    assert str(mean_op_2) == "Mean($volume,10)", f"错误：多级继承下序列化失败，实际为: {str(mean_op_2)}"
    
    # 测试双重包装类，如 Add 继承自 NpPairOperator，NpPairOperator 继承自 PairOperator
    # Add 自定义了构造并显式调用了 super()。我们必须确保父类的包裹器没有用 super 传入的参数覆盖掉 Add 原先捕获的 args。
    add_op = Add(Feature("close"), Feature("open"))
    
    assert add_op.feature_left.name == "close", "错误：双重包裹下 left 属性被父类拦截覆盖！"
    assert add_op.feature_right.name == "open", "错误：双重包裹下 right 属性被父类拦截覆盖！"
    assert str(add_op) == "Add($close,$open)", f"错误：双重包裹下序列化被父类破坏，实际为: {str(add_op)}"
    print("✅ 测试 3 顺利通过！")


    # ──────────────────────────────────────────────────────────────────────────
    # 测试 4: 因子公式编译器解析评估测试 (Formula Parser Compiler)
    # ──────────────────────────────────────────────────────────────────────────
    print("\n👉 测试 4: 因子公式编译器解析评估测试 (parse_field & eval)...")
    
    formula_str = "Mean($close, 20) - Ref($open, 1)"
    python_code = parse_field(formula_str)
    
    expected_code = 'Mean(Feature("close"), 20) - Ref(Feature("open"), 1)'
    assert python_code == expected_code, f"错误：正则转换失败，期待 {expected_code}，实际 {python_code}"
    
    # 建立上下文 Namespace，模拟 eval
    eval_namespace = {
        "Feature": Feature,
        "PFeature": PFeature,
        "Mean": Mean,
        "Ref": Ref,
        "Add": Add,
        "Sub": Sub,
    }
    
    compiled_expr = eval(python_code, eval_namespace)
    assert isinstance(compiled_expr, Sub), "错误：解析后评估得到的对象类型错误！"
    assert str(compiled_expr) == "Sub(Mean($close,20),Ref($open,1))", f"错误：评估后的公式生成错误，实际为: {str(compiled_expr)}"
    print("✅ 测试 4 顺利通过！")

    print("\n======================================================================")
    print("🎉 恭喜！全套单元测试通过！ExpressionOps 动态参数绑定与防覆盖锁完全成功！")
    print("======================================================================")


if __name__ == "__main__":
    run_tests()
