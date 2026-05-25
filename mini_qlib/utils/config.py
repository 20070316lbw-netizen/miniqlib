import duckdb
import yaml
from pathlib import Path

# 项目根目录（当前文件所在目录的上级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ============================================================
# 数据库配置
# ============================================================
DB_DIR = PROJECT_ROOT / "mini_qlib" / "database"
DEFAULT_DB = DB_DIR / "edgar.duckdb"


# ============================================================
# 模型参数和数据切分配置
# ============================================================
DEFAULT_YAML = PROJECT_ROOT / "config.yaml"


# 快捷函数：连接默认数据库
def get_db():
    return duckdb.connect(str(DEFAULT_DB))

# 快捷函数：加载 yaml 配置
def load_config(path: Path = DEFAULT_YAML) -> dict:
    with open(path, "r", encoding="utf-8") as f:   # ← 加 encoding="utf-8"
        return yaml.safe_load(f)
