import duckdb
import pandas as pd
from mini_qlib.utils.config import get_price_db
from mini_qlib.utils.log import get_logger

_log = get_logger(__name__)


def init_prices_table(con: duckdb.DuckDBPyConnection) -> None:
    """
    Initialize prices table if it does not exist (Safe, NO drop table).
    初始化 prices 表（如果不存在），不执行删除操作，确保数据安全。
    """
    con.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            date     DATE,
            ticker   VARCHAR,
            open     DOUBLE,
            high     DOUBLE,
            low      DOUBLE,
            close    DOUBLE,
            volume   BIGINT,
            PRIMARY KEY (date, ticker)
        )
    """)


def insert_prices(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """
    Insert prices into prices table, replacing existing rows on primary key conflict.
    将 DataFrame 写入 prices 表（增量写入，主键冲突时进行替换/更新），并返回写入的行数。
    """
    if df.empty:
        return 0

    # Align column order to match database schema
    # 对齐列顺序以匹配数据库表结构
    df_aligned = df[["date", "ticker", "open", "high", "low", "close", "volume"]]

    con.execute("INSERT OR REPLACE INTO prices SELECT * FROM df_aligned")
    return len(df_aligned)


def get_latest_price_date() -> str | None:
    """
    Query the database to get the latest available price date.
    从数据库查询已有的最新价格日期，若为空或表不存在返回 None。
    """
    with get_price_db(read_only=True) as con:
        try:
            # First ensure table exists
            init_prices_table(con)
            res = con.execute("SELECT MAX(date) FROM prices").fetchone()
            if res and res[0]:
                return res[0].strftime("%Y-%m-%d")
        except Exception as e:
            _log.error("查询最新日期失败: %s", e, exc_info=True)
        return None


def read_prices() -> pd.DataFrame:
    """
    Read all price data from database.
    从数据库读取全部价格数据。
    """
    with get_price_db(read_only=True) as con:
        try:
            return con.execute("SELECT * FROM prices ORDER BY ticker, date").df()
        except duckdb.CatalogException as e:
            # If the prices table does not exist in the database yet, guide the user to fetch data first
            # 如果数据库中尚未创建 prices 行情表，引导用户先运行数据抓取脚本以增量建库
            if "table with name prices does not exist" in str(e).lower():
                _log.warning("数据库中未找到价格行情表 (Table 'prices' not found) 🚨")
                _log.warning("【新手避坑提示】:")
                _log.warning("  说明您的 DuckDB 数据库尚未进行初始化，或未下载任何标的行情数据。")
                _log.warning("  请先在工作区根目录下运行以下数据抓取命令，下载标普500成分股的历史量价数据：")
                _log.warning("     uv run python mini_qlib/scripts/fetch_data.py")
            raise e



if __name__ == "__main__":
    df = read_prices()
    print(f"数据库中共 {len(df)} 行数据")
    if not df.empty:
        print(df.head())
