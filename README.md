# MiniQLib 量化数据与开发工作区 (MiniQLib Quantitative Workspace)

欢迎来到 **MiniQLib** 量化项目工作区！本项目旨在构建一个轻量级、高度模块化的量化研究与回测系统。目前已打通从 **Yahoo Finance** 价格拉取、**SEC EDGAR** 真实财务报表抓取，到本地高效 **DuckDB** 时序与报表数据中心构建的完整数据链路。

---

## 📁 项目目录结构与文件说明 (Directory Structure & Contents)

```text
miniqlib/ (工作区根目录)
├── .gemini/                    # Gemini 智能助手本地配置
│   └── agents/
│       └── translator.md       # 自定义翻译子代理规范 (定义了中英双语注释与 Docstring 强制要求)
├── .vscode/                    # VSCode 工作区特定配置
│   └── settings.json           # VSCode 工作区设置 (已完美配置 DuckDB 插件的自动挂载与默认数据库)
├── EXP_and_LOG/                # 每日研究实验、踩坑与解决案日志系统 (核心知识沉淀区)
│   └── 2026-05-23/
│       └── vscode_duckdb_and_ssl_issues.md # 记录 DuckDB 文件锁冲突、Windows 编码、Clash 代理 SSL 错误的深度解析
├── mini_qlib/                  # 本项目核心源码包 (Core Package)
│   ├── data/                   # 数据加载与处理底层操作
│   │   ├── __init__.py
│   │   ├── load_data.py        # 将拉取的股票价格数据加载写入本地数据库
│   │   └── ops.py              # 底层数据防错与辅助计算操作
│   ├── database/               # 静态与数据库资产区
│   │   └── sp500_tickers.csv   # 标普500成分股列表 (包含 symbol, security, sector, sub_industry)
│   ├── fetcher/                # 高效数据抓取模块 (API 层，遵循中英双语注释规范)
│   │   ├── __init__.py
│   │   ├── fetch_edgar.py      # [NEW] SEC EDGAR 财务报表底层核心抓取与 XBRL 事实解析模块
│   │   ├── fetch_price.py      # 从 Yahoo Finance 批量拉取日 K 线价格数据
│   │   └── get_sp_500_list.py  # 维基百科标普500成分股名单抓取与本地缓存模块 (防御性重试与中文编码支持)
│   ├── scripts/                # 业务调度可执行脚本区 (高层应用层)
│   │   ├── __init__.py
│   │   ├── fetch_data.py       # 执行标普500价格数据抓取并存入数据库
│   │   └── fetch_edgar_runner.py # [NEW] 标普500公司 SEC EDGAR 财务报表一键拉取与 DuckDB 增量入库脚本
│   └── utils/                  # 通用工具包
│       ├── __init__.py
│       └── config.py           # 项目路径、默认数据库连接、YAML 配置文件加载器 (支持 UTF-8 编码防御)
├── qlib/                       # Qlib 量化回测框架集成区
│   └── (尚未开发，保持占位)
├── vectorbt/                   # Vectorbt 矢量回测框架集成区
│   └── (尚未开发，保持占位)
├── zipline-reloaded/           # Zipline-Reloaded 事件驱动回测框架集成区
│   └── (尚未开发，保持占位)
├── sometest/                   # 个人测试沙盒
│   └── (尚未开发，保持占位)
├── config.yaml                 # 全局模型与回测配置参数文件
├── edgar.duckdb                # [NEW] SEC EDGAR 真实财务大数据库文件 (内含 25.8 万条 income/balance/cashflow 记录)
├── main.py                     # 项目入口占位文件
├── pyproject.toml              # 项目依赖配置文件 (已集成 duckdb, pandas, pyyaml, requests, tqdm)
└── uv.lock                     # UV 包管理器锁定文件
```

---

## 🚀 核心功能模块指引 (Core Feature Guides)

### 1. SEC EDGAR 财务数据抓取与入库
* **方法库**：`mini_qlib/fetcher/fetch_edgar.py`  
  支持从美国证券交易委员会（SEC）批量拉取公司 XBRL 财务明细，智能归纳利润表（Income）、资产负债表（Balance）及现金流量表（Cashflow），并自动整理为**无前视偏差的点对点（Point-in-Time）**时序数据。
* **执行器**：`mini_qlib/scripts/fetch_edgar_runner.py`  
  一键拉取标普500成分股的所有报表数据，支持**断点续传**，网络超时自动重试，以及本地代理（Clash）的 SSL 证书安全信任防崩溃机制。

### 2. 标普500成分股维护
* **管理模块**：`mini_qlib/fetcher/get_sp_500_list.py`  
  自动以缓存优先（Cache-First）的原则加载标普500成分股。若本地无缓存，则自动抓取维基百科并以 `utf-8` 编码格式安全固化到本地 CSV，彻底避免了历史回测数据无法复现的问题。

---

## 📝 团队开发契约与规范 (Development Conventions)

为保证项目代码的国际化水准与国内团队极速阅读体验，本项目严格遵守以下两条开发契约：

1. 🌐 **中英双语注释契约 (Bilingual Commenting)**
   所有新编写的底层方法库和高阶脚本，其内的 docstrings、模块说明、关键行代码注释**必须采用英文与中文双语对照编写**（英文在上，精确中文在下），并由 `.gemini/agents/translator.md` 进行自动化规范。
2. 💾 **跨平台 UTF-8 编码契约 (UTF-8 Encoding Defense)**
   由于 Windows 环境的系统默认编码不是 UTF-8，所有涉及到文件读取和写入的操作（如 `open()`、`pd.read_csv()`、`to_csv()`、`yaml.safe_load()`），必须显式指明 `encoding="utf-8"` 参数，严禁使用系统默认编码以防止 `UnicodeDecodeError`。
