# Utilities Module / 基础辅助与全局配置

## 📌 Introduction / 简介
本模块包含项目底层的**全局辅助工具、全局配置管理和数据库连接快捷函数**，是系统各个模块的通用基础支撑。

---

## 📂 Core Utilities / 核心辅助工具
1. **`config.py` (全局配置与环境注册中心)**：
   - 自动推导项目根目录 `PROJECT_ROOT`。
   - 托管数据库路径 `DB_DIR` 与默认日频数据库 `DEFAULT_DB` (指向 `mini_qlib/database/sp500.duckdb`)。
   - 提供 `get_db()` 快捷连接管理器，自动建立并管理 DuckDB 的数据库生命周期。
   - 提供 `load_config()` 用于快速、安全且抗乱码地加载系统 YAML 配置。
