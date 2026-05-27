# Logging 改进方案 (Logging Improvement Plan)

> 创建日期: 2026-05-27
> 关联审计: MiniQLib 核心代码审计报告 P6（风格与可维护性）
> 当前状态: 待执行 (Pending Execution)

---

## 一、现状分析 (Current State Analysis)

当前项目中所有运行时信息输出均使用 Python 内置的 `print()` 函数，分布在以下位置：

| 文件 | 使用场景 | 当前方式 |
| :--- | :--- | :--- |
| `backtest/backtest.py` | 回测进度、NAV、初始化信息 | `print(f"...")` |
| `data/load_data.py` | 数据库未初始化提示、文件锁冲突 | `print("...")` |
| `utils/config.py` | DuckDB 文件锁冲突引导 | `print("...")` |

### 问题 (Issues)

1. **无法控制输出级别**：`print()` 没有 DEBUG / INFO / WARNING / ERROR 的概念，所有输出地位等同，无法在生产环境中按需静默。
2. **无法重定向**：`print()` 默认写 `stdout`，无法灵活路由到文件、syslog 或外部监控系统。
3. **无时间戳/模块名**：排查问题时无法知道每条日志来自哪个模块、何时触发。
4. **与 Python 生态脱节**：第三方库（如 LightGBM、DuckDB）普遍使用 `logging`，混用 `print` 会导致日志流割裂。
5. **多线程/多进程不友好**：`print()` 是非线程安全的缓冲 I/O，在高并发回测中可能产生交错乱码。

---

## 二、目标架构 (Target Architecture)

```
┌─────────────────────────────────────────────────────────┐
│                    mini_qlib Logging Layer               │
├─────────────────────────────────────────────────────────┤
│  mini_qlib.utils.log                                    │  ← 新增：日志工具模块
│  ├── get_logger(name: str) -> logging.Logger            │
│  ├── configure_root(level, format, handlers)            │
│  └── LOG_FORMAT (constant)                              │
├─────────────────────────────────────────────────────────┤
│  各模块使用方式 (Usage Pattern)                          │
│  from mini_qlib.utils.log import get_logger             │
│  _log = get_logger(__name__)                            │
│  _log.info("回测第 %d 天完成", day_idx)                  │
│  _log.warning("DuckDB 文件锁冲突，请关闭 VSCode 连接")    │
│  _log.debug("缓存命中: key=%s", cache_key)               │
└─────────────────────────────────────────────────────────┘
```

### 日志级别约定 (Log Level Convention)

| 级别 | 使用场景 | 生产环境默认 | 示例 |
| :--- | :--- | :--- | :--- |
| `DEBUG` | 缓存命中/未命中、算子子树实例化、正则匹配详情 | ❌ 关闭 | `_log.debug("Compiled formula: %s -> %s", raw, parsed)` |
| `INFO` | 回测进度、数据库连接、脚本阶段标记 | ✅ 开启 | `_log.info("回测第 %3d/%d 天 | NAV = %.2f", i, total, nav)` |
| `WARNING` | 数据缺失回退、文件锁冲突、不推荐的使用方式 | ✅ 开启 | `_log.warning("ticker=%s 当日无收盘价，回退为成本价", ticker)` |
| `ERROR` | 因子编译失败、数据库致命错误、沙箱突破告警 | ✅ 开启 | `_log.error("因子公式编译失败: %s", formula, exc_info=True)` |

---

## 三、实施步骤 (Implementation Steps)

### Step 1: 创建 `mini_qlib/utils/log.py`

```python
# -*- coding: utf-8 -*-
"""
Centralized Logging Configuration for MiniQLib.
MiniQLib 集中式日志配置模块。

Provides a uniform get_logger() interface and a configurable root logger setup,
replacing scattered print() calls with structured, level-aware logging.
提供统一的 get_logger() 接口和可配置的根 logger 设置，
用结构化、分级的日志替代分散的 print() 调用。
"""
import logging
import sys
from pathlib import Path
from typing import Optional

# 默认日志格式：时间 | 级别 | 模块名 | 消息
# Default log format: timestamp | level | module name | message
LOG_FORMAT: str = (
    "%(asctime)s | %(levelname)-7s | %(name)-24s | %(message)s"
)
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# 根 logger 是否已初始化 / Whether root logger has been initialized
_root_configured: bool = False


def configure_root(
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    stream: bool = True,
) -> None:
    """
    配置根 logger 的全局输出级别、格式和处理器。
    Configure the root logger's global output level, format, and handlers.

    Parameters
    ----------
    level : int
        Python logging level (e.g., logging.DEBUG, logging.INFO).
        Python 日志级别（如 logging.DEBUG、logging.INFO）。
    log_file : Path, optional
        可选的日志文件路径；若提供则同时输出到文件。
        Optional log file path; if provided, also write to file.
    stream : bool, default True
        是否输出到 stderr / Whether to output to stderr.
    """
    global _root_configured

    root = logging.getLogger()
    root.setLevel(level)

    # 避免重复添加 handler / Avoid duplicate handlers
    if _root_configured:
        root.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    if stream:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    _root_configured = True


def get_logger(name: str) -> logging.Logger:
    """
    获取或创建指定名称的模块级 logger。
    Get or create a module-level logger with the given name.

    使用惯例 / Usage convention:
        from mini_qlib.utils.log import get_logger
        _log = get_logger(__name__)

    Parameters
    ----------
    name : str
        Logger 名称，通常传入 __name__ / Logger name, typically __name__.

    Returns
    -------
    logging.Logger
        配置好的 logger 实例 / Configured logger instance.
    """
    # 首次调用时自动初始化根 logger / Auto-initialize root logger on first call
    global _root_configured
    if not _root_configured:
        configure_root()
    return logging.getLogger(name)
```

### Step 2: 迁移 `backtest/backtest.py`

将 `print(f"📊 正在初始化...")` 替换为：

```python
from mini_qlib.utils.log import get_logger

_log = get_logger(__name__)

def run_backtest(...) -> pd.DataFrame:
    _log.info("正在初始化事件驱动回测引擎 (Event-driven Backtest initialization)...")
    _log.info("  [账户初始资金] %,.2f USD | [选股做多数量 K] %d 只", initial_cash, K)

    # 进度日志每 100 天输出一次
    if (day_idx + 1) % 100 == 0 or (day_idx + 1) == len(backtest_dates):
        _log.info("  [回测进度] 第 %3d/%d 交易日 | NAV = %,.2f USD", day_idx + 1, total, nav)

    _log.info("事件驱动回测循环圆满完成！共 %d 个交易日", len(history_df))
```

### Step 3: 迁移 `data/load_data.py` 和 `utils/config.py`

将数据库异常提示从 `print()` 迁移到 `_log.warning()` / `_log.error()`。

### Step 4: 补充 DEBUG 日志（可选增强）

在以下关键路径增加 DEBUG 日志，方便排查问题：

- `expression.py:load()` — 缓存命中/未命中
- `handler.py:_compile_single()` — 公式编译详情
- `ops.py:parse_field()` — 正则替换结果
- `exchange.py:match_orders()` — 撮合详情（成交量、滑点、佣金）

---

## 四、向后兼容策略 (Backward Compatibility)

为了不影响现有 `print()` 的使用习惯和已有的控制台输出体验，提供过渡期双轨制：

```python
# mini_qlib/utils/log.py 中可选添加
class PrintToLogAdapter:
    """
    将 logging 输出同时镜像到 stdout，保持与原有 print() 行为一致的终端体验。
    Mirror logging output to stdout to maintain consistent terminal experience.
    """
    def __init__(self, logger: logging.Logger, level: int = logging.INFO):
        self.logger = logger
        self.level = level
    
    def write(self, message: str) -> None:
        if message.strip():
            self.logger.log(self.level, message.rstrip())
    
    def flush(self) -> None:
        pass
```

使用方式：

```python
import sys
from mini_qlib.utils.log import configure_root, PrintToLogAdapter

configure_root(level=logging.DEBUG, log_file=Path("logs/backtest.log"))
sys.stdout = PrintToLogAdapter(get_logger("stdout"))
```

这确保 `print()` 的输出在过渡期仍然可见，同时自动归档到日志文件。

---

## 五、执行优先级 (Execution Priority)

| 步骤 | 影响范围 | 优先级 | 预估工时 |
| :--- | :--- | :--- | :--- |
| Step 1: 创建 log.py | 新文件，零风险 | 🔴 高 | 0.5h |
| Step 2: 迁移 backtest.py | 回测输出 | 🔴 高 | 0.5h |
| Step 3: 迁移 load_data.py / config.py | 数据库提示 | 🟡 中 | 0.5h |
| Step 4: DEBUG 日志 | 增量增强 | 🟢 低 | 1h |
