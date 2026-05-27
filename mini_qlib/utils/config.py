import duckdb
import yaml
from pathlib import Path
from typing import Optional
from mini_qlib.utils.log import get_logger

_log = get_logger(__name__)

# 项目根目录（当前文件所在目录的上级）
# Project root directory (two levels up from this file)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ============================================================
# 数据库配置 / Database Configuration
# ============================================================
DB_DIR = PROJECT_ROOT / "mini_qlib" / "database"
EDGAR_DB = DB_DIR / "edgar.duckdb"      # SEC EDGAR 财务数据库 / financial database
PRICE_DB = DB_DIR / "sp500.duckdb"      # 标普500行情数据库 / market price database
# 向后兼容别名 / Backward-compatible alias
DEFAULT_DB = EDGAR_DB


# ============================================================
# 模型参数和数据切分配置 / Model & Data Split Config
# ============================================================
DEFAULT_YAML = PROJECT_ROOT / "config.yaml"


# 快捷函数：连接 EDGAR 财务数据库 (默认只读, 带 Windows 锁防冲突与新手兜底拦截)
# Quick helper: connect to EDGAR financial database (default read-only, with Windows lock conflict handling)
def get_db(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """
    Connect to the EDGAR financial database.
    连接 EDGAR 财务数据库。

    Parameters
    ----------
    read_only : bool, default True
        Whether to open in read-only mode. Set False only when writing data.
        是否以只读模式打开。仅在写入数据时设为 False。

    Returns
    -------
    duckdb.DuckDBPyConnection
    """
    try:
        return duckdb.connect(str(EDGAR_DB), read_only=read_only)
    except duckdb.IOException as e:
        err_msg = str(e)
        if "already open" in err_msg.lower() or "could not set lock" in err_msg.lower():
            _log.warning("发现 Windows 独占文件锁冲突 (DuckDB Lock Conflict) 🚨")
            _log.warning("【原因剖析】:")
            _log.warning("  当前 DuckDB 数据库文件已被另一个程序以读写/独占模式锁定，导致当前进程无法读取。")
            _log.warning("  报错详情: %s", err_msg.strip())
            _log.warning("【新手秒级避坑指南】:")
            _log.warning("  1. 请检查您的 VSCode，如果您在侧边栏挂载了 DuckDB 数据库连接（如 SQLTools 插件），")
            _log.warning("     请在数据库连接项上点击右键选择 'Disconnect' (断开连接) 释放物理文件锁。")
            _log.warning("  2. 确保没有其他的 Jupyter Notebook 核心或后台运行的 Python 回测进程占用此文件。")
            _log.warning("  3. 释放锁后重新运行此脚本，即可恢复极速计算！")
        raise e


def get_price_db(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """
    Connect to the S&P 500 market price database.
    连接标普500行情价格数据库。

    Parameters
    ----------
    read_only : bool, default True
        Whether to open in read-only mode. Set False only when writing data.
        是否以只读模式打开。仅在写入数据时设为 False。

    Returns
    -------
    duckdb.DuckDBPyConnection
    """
    try:
        return duckdb.connect(str(PRICE_DB), read_only=read_only)
    except duckdb.IOException as e:
        err_msg = str(e)
        if "already open" in err_msg.lower() or "could not set lock" in err_msg.lower():
            _log.warning("发现行情数据库文件锁冲突 (DuckDB Lock Conflict) 🚨")
            _log.warning("  报错详情: %s", err_msg.strip())
        raise e


# 快捷函数：加载 yaml 配置
# Quick helper: load YAML config
def load_config(path: Path = DEFAULT_YAML) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
        if cfg is None:
            _log.warning("配置文件 %s 为空，返回空字典。", path)
            return {}
        return cfg
