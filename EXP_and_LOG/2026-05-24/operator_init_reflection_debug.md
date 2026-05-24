# 2026-05-24 算子初始化反射时序与 Meta-Wrapper 解决方案

## 📌 问题现象与时序瓶颈
在昨天的初步规划中，我们设想在基类 `ExpressionOps.__init__` 中利用 `inspect.signature` 来获取子类的构造函数签名，并以此自动绑定属性：
```python
# 设想中的基类构造
class ExpressionOps(MiniExpression):
    def __init__(self, *args, **kwargs):
        sig = inspect.signature(self.__init__)  # 试图获取子类签名
        ...
```

### 🚨 潜在的两个核心缺陷
1. **构造拦截时序问题 (Reflection Timing)**:
   在 Python 中，如果子类 `Mean` 定义了自己的 `__init__(self, feature, N)`，当其实例化时会先运行 `Mean.__init__`。如果子类在 `Mean.__init__` 内部的第一行或中途调用了 `super().__init__()`，此时控制权才移交给基类 `ExpressionOps.__init__`。
   在基类构造执行时，`self.__init__` 确实指向子类 `Mean.__init__`，但如果子类**忘记**调用了 `super().__init__()`，基类的构造函数将**永远不会执行**，导致所有动态参数属性绑定全部失效！
2. **仍存冗余代码 (Boilerplate)**:
   如果要求每个子类都必须在自己的构造里写一句 `super().__init__(feature, N)`，虽然省去了属性绑定的行数，但依然存在模板代码，且容易因为拼写错误或遗漏调用而引发难以排查的 Bug。

---

## 💡 用户提出的纠偏思路
用户在思考后，一针见血地指出了反射的正确姿势，即通过 `type(self).__init__` 主动反射子类构造，并过滤掉 `self` 参数：
```python
child_init = type(self).__init__
sig = inspect.signature(child_init)
params = [p for p in sig.parameters if p != 'self']
for name, value in zip(params, args):
    setattr(self, name, value)
self.args = args
```
这个方案非常精准，直接将目光锁定在具体的子类类型 `type(self)` 身上，避免了基类自引用时的混淆。

---

## 🚀 终极演进：基于 `__init_subclass__` 的元包装器 (Meta-Wrapper)
为了完美融合用户的反射纠偏思路，并**彻底免除子类调用 `super().__init__()` 的强约束**，我们设计了基于 Python 元编程的 `__init_subclass__` 解决方案：

### 1. 核心原理
`__init_subclass__` 是 Python 3.6+ 引入的高阶类钩子。每当有子类（如 `Rolling` 或 `Mean`）被定义时，Python 会自动调用父类的 `__init_subclass__` 方法。
我们在这个生命周期节点执行“**构造拦截装饰器**”：
* **如果子类定义了自己的 `__init__`**：我们自动把子类的 `__init__` 包裹在一层包装器内。包装器会先执行子类自己的初始化，接着利用 `inspect.signature` 反射子类的参数，自动执行 `setattr` 属性绑定并写入 `self.args`。
* **如果子类没有定义 `__init__`**（例如 `Mean` 继承 `Rolling`）：它会自动继承父类已经被包裹好了的 `__init__`，完美复用参数绑定逻辑。

### 2. 动态参数绑定代码实现蓝图
```python
import inspect

class ExpressionOps(MiniExpression):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        # 只在当前子类显式定义了 __init__ 时对其进行包裹拦截
        if "__init__" in cls.__dict__:
            original_init = cls.__init__
            
            def wrapped_init(self, *args, **kwargs):
                # 1. 执行子类自身的原始初始化逻辑（如参数校验等）
                original_init(self, *args, **kwargs)
                
                # 2. 动态反射获取子类 __init__ 的形参签名
                sig = inspect.signature(original_init)
                bound = sig.bind(self, *args, **kwargs)
                bound.apply_defaults()
                
                # 3. 自动将实参绑定到 self 属性，并填充 self.args
                self.args = []
                for name, value in bound.arguments.items():
                    if name != 'self':
                        setattr(self, name, value)
                        self.args.append(value)
                        
            # 将拦截包装后的 init 回写给子类
            cls.__init__ = wrapped_init
```

---

## 🔏 进阶继承链漏洞防范：参数覆盖与“参数锁（`_params_locked`）”机制

### 1. 多层继承链下的潜在冲突
在更复杂的场景下，我们的算子往往存在多级继承。例如：
`Mean` (叶子算子) $\rightarrow$ `Rolling` (时间窗口抽象算子) $\rightarrow$ `ExpressionOps` (算子基类) $\rightarrow$ `MiniExpression`

如果 `Mean` 和 `Rolling` 都重写了 `__init__`：
1. 类定义时，`Rolling` 和 `Mean` 都会各自触发并注册自己的拦截包装器。
2. 实例化 `Mean($close, 20)` 时，`Mean` 的拦截器被触发，抓取到叶子层参数（如 `feature=$close, N=20`）。
3. 随后，`Mean` 内部在调用原始 `__init__` 时，控制流传导到父类 `Rolling` 包装的 `__init__`。
4. **灾难发生**：如果没有任何保护，父类 `Rolling` 包装器在二次运行时，会重新使用它所看到的签名再次解析参数，从而**强行覆盖**掉子类已经绑定好的最具体参数！

### 2. 完美的解决方案：动态“参数锁”设计
为了彻底封死这一由于继承链嵌套执行导致的参数覆盖漏洞，我们引入了你构想出的参数锁 `_params_locked`：
* 在最外层的包装器（最具体、最末端子类）被触发时，它是第一个拿到全局实际入参并具有最高发言权的。
* 我们在最外层解析成功后，立刻写入一个布尔标识 `self._params_locked = True`，像一把**锁**一样把属性锁定。
* 当调用链向上传导、父类包装器被动运行时，只要检测到 `self._params_locked == True`，就知道叶子类已经完美处理了参数绑定，父类包装器直接**跳过参数绑定与 setattr**，只老老实实执行它本类的原始业务初始化即可。

### 3. 终极完整的 `__init_subclass__` + 参数锁代码结构
```python
import inspect

class ExpressionOps(MiniExpression):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        # 只在当前子类显式定义了 __init__ 时对其进行包裹拦截
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
                    
                    # 动态反射获取子类 __init__ 的形参签名并绑定
                    bound = sig.bind(self, *args, **kwargs)
                    bound.apply_defaults()
                    self.args = []
                    for name, value in bound.arguments.items():
                        if name != 'self':
                            setattr(self, name, value)
                            self.args.append(value)
                
                # 执行本子类的原始初始化逻辑（如参数校验等）
                original_init(self, *args, **kwargs)
                        
            # 将拦截包装后的 init 回写给子类
            cls.__init__ = wrapped_init
```

---

## 💎 这一重构带来的巨大工程优势
1. **子类实现极度纯粹**：子类要么完全不写 `__init__`（如 `Mean` 只需声明类属性 `_func = "mean"` 即可），要么写 `__init__` 只做特定参数校验，**全都不需要**调用 `super().__init__()`，也不需要写任何 `self.xxx = xxx`，全部托管！
2. **规避反射时序隐患**：包装器在类定义时就已经注入，在实例化时，属性在子类 `__init__` 跑完的第一时间被自动绑定，没有任何时序先后或漏调 `super()` 的隐患。
3. **完美阻断嵌套重写**：通过参数锁 `_params_locked`，我们从语言级机制上确保了“继承链中最外层（最具体）的算子参数具有唯一权威性”，杜绝了父类重写干扰。
4. **极大提升调试与测试友好度**：由于参数捕获全部收拢到了基类的包装器中，我们可以非常方便地在包装器内部加上全局 Debug 打印或断点调试（如 `logger.debug(f"Instantiated Operator: {self}")`），这在批量自动化测试和 AST 语法树解析调试时是无价之宝！
