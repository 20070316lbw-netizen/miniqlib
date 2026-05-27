# MiniQLib 通用配置与工具包方法手册 (`mini_qlib/utils`)

本手册详细介绍了 `mini_qlib/utils` 目录下的所有文件、类、方法及路径常量。本模块是整个量化项目的“后台大管家”，负责全局路径解析、数据库连接安全兜底以及 YAML 配置文件跨平台 UTF-8 编码防错读取。

---

## 一、 模块概述 (Module Overview)

`mini_qlib/utils` 目录聚集了项目底层的公共工具包，其核心设计逻辑如下：
1. **绝对路径自动解析**：通过对本文件物理位置的递归追溯，动态得出项目的绝对路径根目录，使得任何子模块的相对调用均不会因为执行脚本时的当前工作目录 (Cwd) 不同而发生路径报错。
2. **Windows 独占文件锁自动拦截**：由于 DuckDB 数据库在 Windows 环境下被另一个进程以写模式打开时，会物理独占文件导致当前进程崩错。工具包内置了对此错误的精准捕获，并打印出新手断开连接的避坑指南。
3. **跨平台 UTF-8 编码契约守护**：强制在所有文件 I/O 读写中采用 `encoding="utf-8"`，彻底屏蔽 Windows 系统默认 GBK 编码带来的致命乱码崩溃。

---

## 二、 文件结构图 (File Structure)

* `config.py`：实现项目根路径、数据库路径的定义，以及共享的 DuckDB 连接池加载器和 YAML 配置文件安全载入器。

---

## 三、 快速参考索引表 (Quick Reference Table)

| 文件名 (File) | 变量/函数名 (Constant/Function) | 变量/函数签名 (Constant/Function Signature) | 作用描述 (Description) |
| :--- | :--- | :--- | :--- |
| **`config.py`** | `PROJECT_ROOT` | `Path` (绝对物理路径对象) | 指向工作区大根目录的绝对路径，用于跨平台文件定位。 |
| | `DEFAULT_DB` | `Path` (DuckDB 物理路径对象) | 指向本地 `edgar.duckdb` 行情与财务数据库的物理路径。 |
| | `DEFAULT_YAML` | `Path` (YAML 配置文件物理路径) | 指向项目全局模型与计算配置文件 `config.yaml`。 |
| | `get_db` | `get_db() -> duckdb.DuckDBPyConnection` | 极速连接默认 DuckDB 数据库，内置 Windows 锁冲突捕获。 |
| | `load_config` | `load_config(path=DEFAULT_YAML) -> dict` | 跨平台以 UTF-8 编码安全读取并解析任意 YAML 配置文件。 |

---

## 四 & 五、 核心 API 教学与极速开始示例 (Detailed API & Quick-Start Examples)

### 1. 绝对路径解析 (Cross-platform Absolute Path Consts)
* **`PROJECT_ROOT`**:
  在代码中，我们通过以下魔法语句动态定位大根目录：
  ```python
  PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
  ```
  这使得无论你在任何子目录中执行代码，它在物理定位时都能干净地解析到大根目录下，极佳地降低了多项目工作区下的文件读取门槛。

---

### 2. 数据库连接兜底 (`get_db`)
* **`get_db() -> duckdb.DuckDBPyConnection`**
  * **英文**: Connects to the default DuckDB database in read-only mode. Intercepts Windows-specific独占 file locks and prints user-friendly debugging logs to release the lock.
  * **中文**: 以**只读模式（Read-Only）**连接至默认 DuckDB 数据库。当检测到 Windows 物理锁 IO 异常（即该文件已被其他 Jupyter Notebook、SQL 插件或后台进程独占占用）时，精准拦截，并以 Emoji 打印出秒级解决方案，保护程序不发生野蛮崩溃。

---

### 3. 配置读取与 UTF-8 防护 (`load_config`)
* **`load_config(path: Path = DEFAULT_YAML) -> dict`**
  * **中文说明**: 跨平台加载 YAML。强行设定 `encoding="utf-8"` 参数，避开 Windows 环境下系统编码不一致的千古大坑。

---

### 4. 极速开始示例 (Quick-Start Examples)

以下是完整可直接运行的独立测试脚本，展示了初学者如何调用工具包安全加载 YAML、安全打开只读数据库连接并打印避坑指引：

```python
import sys
from pathlib import Path

# Add project root to sys.path to enable clean imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "mini_qlib"))

from mini_qlib.utils.config import PROJECT_ROOT, DEFAULT_DB, get_db, load_config

# 1. 打印全局绝对路径，检查其跨平台解析是否正确
print("🎬 绝对路径全局盘点 (Paths Constants):")
print(f"   项目根目录 (PROJECT_ROOT): {PROJECT_ROOT}")
print(f"   默认 DuckDB 数据库路径 (DEFAULT_DB): {DEFAULT_DB}")

# 2. 调用 get_db 安全打开只读连接，抓取并查询行情数据库
print("\n🎬 启动只读数据库连接...")
try:
    with get_db() as con:
        # 查询 prices 行情表中的前 3 只 AAPL 数据
        # 若表不存在会触发异常，此处用 try-except 进行安全防错
        res = con.execute("SELECT * FROM prices WHERE ticker='AAPL' LIMIT 3").df()
        print("   ✅ 连接成功！AAPL 行情数据样例:")
        print(res)
except Exception as e:
    print(f"   ℹ️ 数据库尚未初始化或当前无可查询行情 (正常表现，请运行数据抓取脚本): {e}")

# 3. 调用 load_config 跨平台 UTF-8 安全加载 YAML 配置文件
pipeline_yaml = PROJECT_ROOT / "config_pipeline.yaml"
print(f"\n🎬 跨平台以 UTF-8 安全载入 YAML 配置: {pipeline_yaml}")
try:
    cfg = load_config(pipeline_yaml)
    print("   ✅ 加载并解析成功！因子与标签组装配置摘要:")
    print(f"       特征列表: {list(cfg.get('data_handler', {}).get('features', {}).keys())}")
    print(f"       预测标签: {cfg.get('data_handler', {}).get('labels', {})}")
except FileNotFoundError:
    print("   ❌ 未找到 `config_pipeline.yaml` 配置文件，请检查大根目录下文件完整性！")
```
