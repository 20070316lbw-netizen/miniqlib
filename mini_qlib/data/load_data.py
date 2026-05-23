import duckdb
import pandas as pd
from utils.config import get_db, DEFAULT_DB


def create_prices_table(con: duckdb.DuckDBPyConnection) -> None:
    """建 prices 表（如已存在则先删除）"""
    # TODO
    con.execute("DROP TABLE IF EXISTS prices")
    con.execute("""
        CREATE TABLE prices (
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
    """将 DataFrame 写入 prices 表，返回写入行数"""
    con.execute("INSERT INTO prices SELECT * FROM df")
    count = con.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    return count


def load_prices(df: pd.DataFrame) -> int:
    """
    一步完成建表 + 写入：传入 DataFrame，写进数据库，返回写入行数
    每次调用会清空重建 prices 表
    """
    with duckdb.connect(str(DEFAULT_DB)) as con:
        create_prices_table(con)
        return insert_prices(con, df)


def read_prices() -> pd.DataFrame:
    """从数据库读取全部 prices 数据"""
    with get_db() as con:
        return con.execute("SELECT * FROM prices ORDER BY ticker, date").df()


if __name__ == "__main__":
    df = read_prices()
    print(f"数据库中共 {len(df)} 行")
    print(df.head())
