# MiniQLib 统一量化多项目工作区 (Unified Quant-Lab Workspace)

[![Python](https://img.shields.io/badge/Python-3.10-blue.svg?style=flat-square&logo=python)](https://www.python.org/)
[![Package Manager](https://img.shields.io/badge/uv-workspace-green.svg?style=flat-square)](https://github.com/astral-sh/uv)
[![Architecture](https://img.shields.io/badge/Architecture-Monorepo-orange.svg?style=flat-square)](https://github.com/20070316lbw-netizen/miniqlib)
[![License](https://img.shields.io/badge/License-MIT-purple.svg?style=flat-square)](LICENSE)

欢迎来到 **MiniQLib** 统一量化多项目工作区！这是一个基于 **`uv workspace`** 技术构建的高性能量化开发和研究环境。

本项目完美实现了“**数据链路 + 三大主流回测与分析引擎**”的同仓管理。通过根目录的一键依赖托管，你可以在同一个 Python 虚拟环境中无冲突地调用 `Qlib`、`VectorBT` 和 `Zipline`，彻底解决了经典量化库版本冲突的“千古难题”。

---

## 💡 开源复刻与衍生声明 (Fork & Derivative Declarations)

本工作区在本地以子项目的形式集成了以下三大顶级量化金融开源框架。虽然为了日常开发的一键提交与统一管理，我们将它们合并到了本工作区单仓中，但我们在此郑重声明并致敬以下原版项目：

| 子项目名称 (Sub-Project) | 衍生自上游原始仓库 (Derived From) | 授权协议 (License) | 说明 (Notes) |
| :--- | :--- | :--- | :--- |
| **`qlib`** | 🍴 [microsoft/qlib](https://github.com/microsoft/qlib) | MIT | 微软 AI 量化投资与机器学习平台，完美保留历史 Commit |
| **`vectorbt`** | 🍴 [polakowo/vectorbt](https://github.com/polakowo/vectorbt) | Apache-2.0 | 基于 NumPy/Numba 的超高速矢量回测与分析引擎 |
| **`zipline-reloaded`** | 🍴 [stefan-jansen/zipline-reloaded](https://github.com/stefan-jansen/zipline-reloaded) | Apache-2.0 | 支持多因子与事件驱动的回测引擎（Zipline 的现代化维护分支） |

> 💡 **小贴士**：本仓库中这三个子项目的全部代码和历史 commit 均已完美搬迁至子目录下，任何对这三个库的底层修改都会统一保存在本工作区中。

---

## 📁 项目目录结构与文件说明 (Directory Structure & Contents)

```text
miniqlib/ (工作区大根目录)
├── .gemini/                    # Gemini 智能助手本地配置
│   └── agents/
│       └── translator.md       # 自定义翻译子代理规范 (中英双语注释与 Docstring 强制要求)
├── .venv/                      # [自动生成] 由 uv workspace 编译的统一高速虚拟环境
├── .vscode/                    # VSCode 工作区特定配置
│   └── settings.json           # VSCode 工作区设置 (已完美配置 DuckDB 插件的自动挂载)
├── EXP_and_LOG/                # 每日研究实验、踩坑与解决案日志系统 (核心知识沉淀区)
│   └── 2026-05-23/
│       └── vscode_duckdb_and_ssl_issues.md # 记录 DuckDB 文件锁冲突、编码、代理 SSL 错误的解析
├── mini_qlib/                  # 本项目原生数据与研究模块 (Core Package)
│   ├── data/                   # 数据加载与处理底层操作
│   │   ├── load_data.py        # 将拉取的股票价格数据加载写入本地数据库
│   │   └── ops.py              # 底层数据防错与辅助计算操作
│   ├── database/               # 静态与数据库资产区
│   │   └── sp500_tickers.csv   # 标普500成分股列表
│   ├── fetcher/                # 高效数据抓取模块 (API 层，遵循中英双语注释规范)
│   │   ├── fetch_edgar.py      # SEC EDGAR 财务报表底层核心抓取与 XBRL 事实解析模块
│   │   ├── fetch_price.py      # 从 Yahoo Finance 批量拉取日 K 线价格数据
│   │   └── get_sp_500_list.py  # 维基百科标普500成分股名单抓取与本地缓存模块
│   ├── scripts/                # 业务调度可执行脚本区 (高层应用层)
│   │   ├── fetch_data.py       # 执行标普500价格数据抓取并存入数据库
│   │   └── fetch_edgar_runner.py # 标普500公司 SEC EDGAR 财务报表一键拉取与 DuckDB 增量入库脚本
│   └── utils/                  # 通用工具包
│       └── config.py           # 项目路径、默认数据库连接、YAML 配置文件加载器
│
# ─── 统一托管的三大顶级量化框架子项目 (UV Workspace Members) ───
├── qlib/                       # [Workspace Member] Microsoft Qlib 框架目录 (带完整历史)
├── vectorbt/                   # [Workspace Member] VectorBT 矢量回测引擎目录
├── zipline-reloaded/           # [Workspace Member] Zipline 因子回测引擎目录 (Cython 加速)
│
├── sometest/                   # 个人测试沙盒
├── config.yaml                 # 全局模型与回测配置参数文件
├── edgar.duckdb                # SEC EDGAR 真实财务大数据库文件
├── pyproject.toml              # [核心配置] 声明 uv workspace 架构和跨项目依赖关系
└── uv.lock                     # [自动生成] 锁定的工作区全量依赖树
```

---

## ⚡ 现代 Workspace 环境极速上手指南 (Modern Workspace Guide)

本工作区使用超高速 Python 包管理器 [**`uv`**](https://github.com/astral-sh/uv) 统一管理：

### 1. 一键同步并安装全部依赖 (包括三大子项目)
在工作区根目录下打开终端，直接运行：
```powershell
uv sync
```
这行命令会：
* 自动检测 `.python-version`，在本地安装 Python 3.10.x（如果不存在的话）；
* 为这三个子项目（`qlib`、`vectorbt`、`zipline`）编译它们所需的 Cython 与底层二进制依赖；
* **以 `editable` (可编辑开发) 的形式**直接将它们软链接安装到根目录的统一 `.venv` 虚拟环境中！

### 2. 启动共享的研究工作台 (Jupyter Lab)
在根目录下运行：
```powershell
uv run jupyter lab
```
在打开的 Jupyter Notebook 中，你可以直接在同一个 Kernel 里同时运行：
```python
import qlib
import vectorbt as vbt
import zipline
print("🚀 三大引擎完美共存！")
```

---

## 📝 团队开发契约与规范 (Development Conventions)

为保证项目代码的国际化水准与团队阅读体验，本项目严格遵守以下两条开发契约：

1. 🌐 **中英双语注释契约 (Bilingual Commenting)**
   所有新编写的底层方法库和高阶脚本，其内的 docstrings、模块说明、关键行代码注释**必须采用英文与中文双语对照编写**（英文在上，精确中文在下），并由 `.gemini/agents/translator.md` 进行自动化规范。
2. 💾 **跨平台 UTF-8 编码契约 (UTF-8 Encoding Defense)**
   由于 Windows 环境的系统默认编码不是 UTF-8，所有涉及到文件读取和写入的操作（如 `open()`、`pd.read_csv()`、`to_csv()`、`yaml.safe_load()`），必须显式指明 `encoding="utf-8"` 参数，严禁使用系统默认编码以防止 `UnicodeDecodeError`。
