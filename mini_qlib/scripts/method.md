# MiniQLib 业务调度与流水线脚本方法手册 (`mini_qlib/scripts`)

本手册详细介绍了 `mini_qlib/scripts` 目录下的所有核心文件、类、方法及调度函数。本模块是项目的“总指挥台”，负责一键启动增量数据抓取、财务大数据库合并以及配置链驱动的工业级量化流水线。

---

## 一、 模块概述 (Module Overview)

`mini_qlib/scripts` 目录聚集了高层的可执行业务脚本。这些脚本把底层的数据加载、算子计算、物理撮合等散装模块，拼装成完整的自动化作业流：
```text
                  [ config_pipeline.yaml 配置文件 ]
                                 │
                                 ▼ (一键启动 run_pipeline.py)
   ┌─────────────────────────────┼─────────────────────────────┐
   ▼                             ▼                             ▼
数据自动读取与结算             时序隔离带安全分割             LightGBM 模型训练与
DataHandler 因子生成          Embargo 交易日顺延             Early-Stopping 优化
   │                             │                             │
   └─────────────────────────────┼─────────────────────────────┘
                                 ▼
                     📊 横截面多维业绩评估 (Rank IC/IR)
                                 │
                                 ▼
                     🏁 高保真等权重 Top-K 轮动回测
```

---

## 二、 文件结构图 (File Structure)

* `fetch_data.py`：增量价格数据抓取和补充新数据的可执行调度脚本。
* `fetch_edgar_runner.py`：一键下载并解析标普 500 所有公司财务数据入库 DuckDB 的可执行调度脚本。
* `run_pipeline.py`：配置链驱动的量化特征编译、安全时空切分、机器学习模型训练、Rank IC 评估及事件回测的一站式闭环主流水线。

---

## 三、 快速参考索引表 (Quick Reference Table)

| 文件名 (File) | 函数名 (Function) | 函数签名 (Function Signature) | 作用描述 (Description) |
| :--- | :--- | :--- | :--- |
| **`fetch_data.py`** | `fetch_and_supplement_prices` | `fetch_and_supplement_prices(tickers, overlap_days=5, force_full=False) -> int` | 执行增量拉取价格行情并合并合并写入数据库。 |
| **`run_pipeline.py`**| `calculate_embargo_dates` | `calculate_embargo_dates(dates, train_end, valid_end, embargo_days) -> (Timestamp, Timestamp)` | 时序切分隔离带计算，避开未来信息泄露。 |
| | `evaluate_rank_ic` | `evaluate_rank_ic(pred: pd.Series, label: pd.Series) -> pd.DataFrame` | 计算横截面 Spearman Rank IC 并输出多维统计表。 |
| | `main` | `main()` | 一站式量化多因子与事件驱动回测闭环大调度器。 |
| **`fetch_edgar_runner.py`** | `main` | `main()` | SEC EDGAR 公司事实大批量下载与断点续传。 |

---

## 四、 核心调度算法与原理解析 (Core Algorithms & Principles)

### 1. `run_pipeline.py` — 配置链主流水线

本文件是 MiniQLib 的旗舰入口，内置了数个极其关键的量化研究调度算法：

#### 🔴 `calculate_embargo_dates`（时序分割隔离带算法）
在多因子截面研究中，为了预测未来，我们计算的 `label` 天然包含未来信息（如未来 5 日收益 `label_5d`）。如果在时序分割训练集与验证集时，**仅仅以简单日期直接切割（例如 2021-12-31 结束训练，2022-01-01 开始验证），则 2021-12-31 倒数那几天的 Label 已经偷看了 2022 年 1 月初的价格！** 这会导致验证集表现出现严重的前瞻虚高。

* **`calculate_embargo_dates(dates: pd.DatetimeIndex, train_end: pd.Timestamp, valid_end: pd.Timestamp, embargo_days: int) -> Tuple[pd.Timestamp, pd.Timestamp]`**
  * **原理**:
    本算法基于真实的交易日历列表（`dates`），自动在训练集结束点 `train_end` 向后**强行顺延 `embargo_days`（如 6 个交易日）作为“物理隔离带”**。隔离带内的样本全部作废剔除，使得验证集真正的起始日 `valid_start` 避开数据重叠，**物理粉碎前瞻偏差**。同理在验证集与测试集边界也进行同样的 Embargo 顺延保护。

* **`evaluate_rank_ic(pred: pd.Series, label: pd.Series) -> pd.DataFrame`**
  * **中文说明**: 计算横截面 Spearman 秩相关系数（Rank IC）。
  * **多维度统计**:
    - **Rank IC 均值**：代表因子选股能力的平均强度（一般大于 0.02 代表具有极佳阿尔法能力）。
    - **Rank IC 标准差**：因子的波动。
    - **信息比率 (IR)**：`IC 均值 / IC 标准差`，代表因子收益的稳定程度（通常大于 0.5 极为优秀）。
    - **t 统计量 (t-stat)**：`IC_mean / (IC_std / sqrt(N))`，用于显著性检验。若 $|t| > 1.96$，说明因子在 95% 置信度下显著非零。
    - **胜率 (Win Ratio)**：Rank IC 值为正的交易日占比。

---

### 2. `fetch_data.py` — 增量行情抓取调度

* **`fetch_and_supplement_prices(tickers: list[str], overlap_days: int = 5, force_full: bool = False) -> int`**
  * **增量设计原理解析**:
    1. 首先查询本地 DuckDB，调用 `get_latest_price_date()` 自动获取数据库中已有的最新价格日期（例如 `2026-05-15`）。
    2. 若已有最新日期，自动切换为**“增量补充模式”**：抓取起始日设为 `latest_date - overlap_days`（减去重叠天数，以兼容不同时区、未开盘周末等数据空洞），截止日设为今天。
    3. 若无数据，自动切换为**“全量拉取模式”**：默认一次性下载过去 10 年的所有历史量价（秒级增量建库）。

---

## 五 & 六、 初学者一键流水线极速运行指南 (Quick-Start Guide)

本脚本展示了初学者如何在工作区根目录下，直接通过命令行或代码拉起整个配置链流水线。

### 1. 命令行一键运行
在 VSCode 终端或 Windows PowerShell 中，直接输入以下命令，即可一键闭环运行全套量化因子编译、训练与回测：
```powershell
uv run python mini_qlib/scripts/run_pipeline.py
```

### 2. Python 代码内调度运行演示
以下是完整代码，展示了初学者如何加载 `config_pipeline.yaml`，提取其切分配置并手动核算安全隔离带日期：

```python
import sys
import yaml
import pandas as pd
from pathlib import Path

# Add project root to python path to prevent ModuleNotFoundError
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "mini_qlib"))

from mini_qlib.scripts.run_pipeline import calculate_embargo_dates, evaluate_rank_ic

# 1. 读取工作区根目录下的流水线 YAML 配置文件
config_path = PROJECT_ROOT / "config_pipeline.yaml"
print(f"📂 正在加载流水线配置: {config_path}")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# 2. 盘点配置中的数据集切分点
seg = config["data_loader"]["segments"]
train_end = pd.Timestamp(seg["train"]["end"])
valid_end = pd.Timestamp(seg["valid"]["end"])
embargo_days = config["data_loader"].get("embargo_days", 6)

print(f"   [配置参数] 训练结束日 (train_end): {train_end.strftime('%Y-%m-%d')}")
print(f"   [配置参数] 验证结束日 (valid_end): {valid_end.strftime('%Y-%m-%d')}")
print(f"   [配置参数] 隔离带顺延天数 (embargo_days): {embargo_days} 天")

# 3. 构造模拟的连续交易日历
mock_trading_days = pd.date_range("2021-12-25", periods=20, freq="B")

# 4. 调用 calculate_embargo_dates 核心算法顺延交易日
valid_start, test_start = calculate_embargo_dates(
    dates=mock_trading_days,
    train_end=train_end,
    valid_end=valid_end,
    embargo_days=embargo_days
)

print(f"\n🛡️ 安全隔离带 (Embargo) 时序切分结果:")
print(f"   原设定验证集起始点: {seg['valid']['start']}")
print(f"   ➡️ 交易日顺延后【安全验证集起始日】: {valid_start.strftime('%Y-%m-%d')} (已成功避开前瞻泄露区间)")

# 5. 模拟一次 Rank IC 统计评估
# 构造 3 天的模拟因子预测值与真实未来收益
mock_pred = pd.Series([0.1, 0.5, 0.3, 0.2, 0.4, 0.6], 
                      index=pd.MultiIndex.from_product([pd.date_range("2026-05-01", periods=3), ["AAPL", "MSFT"]], names=["date", "ticker"]))
mock_label = pd.Series([0.02, 0.08, -0.01, 0.03, 0.05, 0.07], index=mock_pred.index)

ic_report = evaluate_rank_ic(mock_pred, mock_label)
print("\n📊 模拟 Rank IC 因子业绩报告样板:")
print(ic_report.to_string(index=False))
```
