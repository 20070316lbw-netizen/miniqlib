# MiniQLib 注册制因子与标签库方法手册 (`mini_qlib/factor`)

本手册详细介绍了 `mini_qlib/factor` 目录下的所有核心文件、类、方法及注册特征。本模块是项目的“因子超市”，采用解耦的“注册表 (Registry) 机制”，方便研究员按名索骥获取因子，也支持纯 AST 算子对象的直接调用。

---

## 一、 模块概述 (Module Overview)

在工业级量化框架中，因子的管理极其庞杂。`mini_qlib/factor` 目录通过构建全局的注册表实例，解决了两个痛点：
1. **防冗余硬编码**：新因子只需写一次公式并调用 `register()` 注册，全局即可通过名字（如 `"KMID"`）在配置文件中任意组合调用。
2. **完美支持多态入参**：底层计算网关 `DataHandler` 在解析注册因子时，既兼容纯字符串公式，也兼容预先装配的纯 AST 算子对象，具有极高架构弹性。

---

## 二、 文件结构图 (File Structure)

* `feature.py`：实现经典量化特征（因子）的注册中心 `FeatureRegistry`，并内置微软 Qlib 的经典 Alpha158 特征子集（KMID、KLEN、ROC 等）。
* `label.py`：实现机器学习预测标签的注册中心 `LabelRegistry`，内置含有交易开仓延迟（gap）的多周期超额收益标签。

---

## 三、 快速参考索引表 (Quick Reference Table)

| 文件名 (File) | 类名/函数名 (Class/Function) | 方法/函数签名 (Method/Function Signature) | 作用描述 (Description) |
| :--- | :--- | :--- | :--- |
| **`feature.py`** | `FeatureRegistry` | `register(name, expr, desc="")` | 注册一个特征公式或 AST 特征。 |
| | | `get(name) -> Union[str, MiniExpression]` | 获取已注册的特征表达式或 AST。 |
| | | `get_description(name) -> str` | 获取特征的中文业务含义。 |
| | | `list_all() -> List[str]` | 列出所有已注册的特征名称列表。 |
| **`label.py`** | `LabelRegistry` | `register(name, expr, desc="")` | 注册一个预测收益标签。 |
| | | `get(name) -> Union[str, MiniExpression]` | 获取已注册的标签。 |
| | | `get_description(name) -> str` | 获取标签的中文业务说明。 |

---

## 四、 核心 API 教学与经典注册因子列表 (Detailed API & Catalog)

### 1. 注册管理核心 API (`FeatureRegistry` & `LabelRegistry`)

两个类均支持相同的生命周期操作：

* **`register(name: str, expr: Union[str, MiniExpression], desc: str = "")`**
  * **英文**: Registers a new factor string formula or pre-built AST operator into the registry map.
  * **中文**: 向注册表中填装一个新的特征公式字串或预构建的 AST 算子节点，并绑定其中文业务说明。
  * **示例**:
    ```python
    feature_registry.register("MY_CLOSE", "$close", "收盘价基础特征")
    ```

---

### 2. 经典已注册特征列表 (Pre-registered Alpha158 Subset)

`mini_qlib/factor/feature.py` 中已经预装了以下经典的量化特征，初学者可在 `config_pipeline.yaml` 的 `features` 配置中直接写名字调用：

#### 🔴 K线形态特征 (K-Bar Shapes)
* **`KMID`**（K线实体涨跌幅比例）: `($close-$open)/$open`
  * 解释：当日收盘相对开盘的涨跌幅。
* **`KLEN`**（K线全天振幅比率）: `($high-$low)/$open`
  * 解释：当日最高最低宽幅占开盘的比例。
* **`KMID2`**（影线与实体比率）: `($close-$open)/($high-$low+1e-12)`
  * 解释：实体占全天振幅的权重比例，常用于捕捉多空博弈强弱。
* **`KUP`**（上影线长度占比）: `($high-Greater($open,$close))/$open`
  * 解释：实体上沿到最高点的振幅占比。
* **`KLOW`**（下影线长度占比）: `(Less($open,$close)-$low)/$open`
  * 解释：最低点到实体下沿的振幅占比。
* **`KSFT`**（收盘价偏离中枢度）: `(2*$close-$high-$low)/$open`
  * 解释：收盘价在全天价格中轴的上下侧偏离深度。

#### 🔴 时序滚动特征 (Rolling Series)
* **`ROC5`** / **`ROC10`**（5日/10日价格滚动动量）: `Ref($close,N)/$close`
  * 解释：历史价格相对当前价格的比例（经典的 Qlib 标准除法形式）。
* **`MA5`** / **`MA10`**（5日/10日移动平均偏离度）: `Mean($close,N)/$close-1`
  * 解释：均线系统相对当前股价的偏离程度。
* **`STD5`**（5日收盘价滚动标准差）: `Std($close,5)/$close`
  * 解释：历史滚动波动率，除以 `close` 以消除股价量级影响。
* **`VMA10`**（10日成交量移动平均偏离度）: `Mean($volume,10)/($volume+1e-12)-1`
  * 解释：均量系统相对当前成交量的偏离，用于捕捉异常放量。
* **`RSV5`**（5日随机随机指标）: `($close-Min($low,5))/(Max($high,5)-Min($low,5)+1e-12)`
  * 解释：股价在过去 5 日最低最高震荡区间内的相对高低位置。

---

### 3. 经典已注册预测标签列表 (Pre-registered Forward Return Labels)

在量化多因子研究中，因子的评估与训练依赖“未来超额收益”。由于 $T$ 日收盘时因子决策刚做出，**实盘中在 $T$ 日 Close 时是无法立刻买入的**，必须给策略留出一个 Bar 的进场滞后（gap）。

`mini_qlib/factor/label.py` 中预先注册了以下带有 1 期交易时延的未来收益标签：

* **`label_1d`**（未来 1 日持仓收益率）: `Ref($close, -2) / Ref($close, -1) - 1`
  * **原理解析**:
    - `Ref($close, -1)` 代表 $T+1$ 日的收盘价（买入价格）。
    - `Ref($close, -2)` 代表 $T+2$ 日的收盘价（卖出价格）。
    - 此公式严格对应了“在 $T$ 日 Close 根据因子得分下达决策，在 $T+1$ 日执行开仓，并持有至 $T+2$ 日收盘清仓”的**无未来函数纯净时序收益**。
* **`label_5d`**（未来 5 日持仓收益率）: `Ref($close, -6) / Ref($close, -1) - 1`
  * 解释：$T+1$ 日收盘买入，持有 5 个交易日，在 $T+6$ 日收盘清仓。
* **`label_10d`** / **`label_20d`**：分别为持有 10 天和 20 天的未来持仓收益率。

---

## 五 & 六、 初学者极速开始示例 (Quick-Start for Beginners)

以下是完整可运行的独立示例，展示了初学者如何查询已注册的因子、中文含义描述，以及如何自己设计注册一个全新的因子：

```python
import pandas as pd
from mini_qlib.factor import feature_registry, label_registry
from mini_qlib.data.expression import Feature
from mini_qlib.data.handler import DataHandler

# 1. 探索“因子超市”中现有的因子与中文描述
print("🛒 当前特征超市中拥有的经典因子:")
all_features = feature_registry.list_all()
for name in all_features:
    desc = feature_registry.get_description(name)
    print(f"   - {name:<12} | {desc}")

# 2. 探索“标签超市”中的未来收益标签
print("\n🛒 当前标签超市中拥有的预测标签:")
for name in label_registry.list_all():
    desc = label_registry.get_description(name)
    print(f"   - {name:<12} | {desc}")

# 3. 初学者自定义：我们来设计一个全新的“乖离率”因子并注册进库
# 公式：(收盘价 - 10日移动平均线) / 10日移动平均线
feature_registry.register(
    name="BIAS10",
    expr="($close - Mean($close, 10)) / Mean($close, 10)",
    desc="10日股价乖离率：测算当日收盘价与10日均线的距离"
)

print(f"\n🆕 成功注册新因子 'BIAS10'！")
print(f"   公式: {feature_registry.get('BIAS10')}")
print(f"   描述: {feature_registry.get_description('BIAS10')}")

# 4. 模拟行情计算
records = [
    {"date": "2026-05-01", "ticker": "AAPL", "open": 100.0, "close": 102.0},
    {"date": "2026-05-02", "ticker": "AAPL", "open": 102.0, "close": 105.0},
]
df = pd.DataFrame(records)
df["date"] = pd.to_datetime(df["date"])
df = df.set_index(["date", "ticker"]).sort_index()

# 5. 直接在配置流水线中按名字引用新因子
config = {
    "features": {
        "AM_I_BIAS": "BIAS10"  # 直接写刚注册的名字！
    },
    "labels": {
        "lbl": "label_1d"
    }
}

handler = DataHandler(df, config)
# 由于我们均线窗口为 10 天，而模拟数据只有 2 天，此处由于有效观测不足，输出为 NaN（符合滚动隔离预期）
print("\n📊 自动装配计算完成:")
print(handler.setup())
```
