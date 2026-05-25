# ==============================================================================
# ABSOLUTE FILE PATH: C:\Users\liu\Desktop\miniqlib\mini_qlib\scripts\fetch_edgar_runner.py
# DESCRIPTION: Executable script to download S&P 500 company financial reports from SEC EDGAR.
# 描述: 用于从 SEC EDGAR 下载标普500成分股公司财务报表的可执行脚本。
# WARNING: This is an executable script. Run it in a terminal environment.
# 警告: 这是一个可执行脚本。请在终端环境中运行它。
# ==============================================================================

import sys
from pathlib import Path

# Add project root to sys.path to enable clean imports
# 将项目根目录添加到 sys.path 以支持干净的绝对导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb
import pandas as pd
import time
from tqdm import tqdm
from fetcher.fetch_edgar import (
    get_cik_map,
    fetch_company_facts,
    facts_to_df,
    init_db,
    already_done,
    save_df,
    INCOME_CONCEPTS,
    BALANCE_CONCEPTS,
    CASHFLOW_CONCEPTS
)

# ── CONFIG / 运行配置 ─────────────────────────────────────────────────────────

import yaml

# Resolve project root and load private config
# 获取项目根目录并加载私有配置文件
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH  = PROJECT_ROOT / "config_private.yaml"

edgar_email = "your_email@example.com" # Default placeholder / 默认占位邮箱
if CONFIG_PATH.exists():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            private_config = yaml.safe_load(f) or {}
            edgar_email = private_config.get("edgar_email", edgar_email)
    except Exception as e:
        print(f"警告：读取私有配置文件失败，将使用默认邮箱。错误：{e}")

DB_PATH    = str(PROJECT_ROOT / "mini_qlib" / "database" / "edgar.duckdb")
HEADERS    = {"User-Agent": edgar_email}  # ← SEC EDGAR User-Agent / 用户标识
RATE_LIMIT = 0.12  # Rate limit to comply with SEC (10 reqs/sec) / 限速以符合 SEC 要求（10次/秒）

def main():
    # Fix Windows console emoji printing error
    # 修复 Windows 控制台下 Emoji 打印可能出现的编码错误
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    con = duckdb.connect(DB_PATH)
    init_db(con)

    # Load S&P 500 tickers from CSV
    # 从本地 CSV 文件加载标普500成分股列表
    csv_path = Path(__file__).resolve().parent.parent / "database" / "sp500_tickers.csv"
    sp500_tickers = pd.read_csv(csv_path, encoding="utf-8")["symbol"].tolist()

    print(f"准备下载 {len(sp500_tickers)} 家公司...")
    print(f"数据库：{Path(DB_PATH).resolve()}\n")

    print("获取CIK映射表...")
    try:
        cik_map = get_cik_map(headers=HEADERS)
    except Exception as e:
        print(f"获取CIK映射表失败: {e}")
        con.close()
        sys.exit(1)
    
    time.sleep(RATE_LIMIT)

    failed = []

    for ticker in tqdm(sp500_tickers, desc="下载进度"):
        # Skip if already downloaded (breakpoint resume)
        # 断点续传：若该公司已下载完毕，则直接跳过
        if already_done(con, ticker):
            continue

        cik = cik_map.get(ticker.upper())
        if not cik:
            failed.append((ticker, "CIK未找到"))
            continue

        # Fetch facts
        # 拉取公司财务事实数据
        facts = fetch_company_facts(cik, headers=HEADERS)
        time.sleep(RATE_LIMIT)

        if not facts:
            failed.append((ticker, "EDGAR无数据"))
            con.execute(
                "INSERT OR REPLACE INTO download_log VALUES (?,?,current_timestamp)",
                [ticker, "failed"]
            )
            continue

        # Parse and save to corresponding tables
        # 解析数据并存入相应的 DuckDB 数据表
        save_df(con, "income",   facts_to_df(facts, INCOME_CONCEPTS,   ticker))
        save_df(con, "balance",  facts_to_df(facts, BALANCE_CONCEPTS,  ticker))
        save_df(con, "cashflow", facts_to_df(facts, CASHFLOW_CONCEPTS, ticker))

        con.execute(
            "INSERT OR REPLACE INTO download_log VALUES (?,?,current_timestamp)",
            [ticker, "ok"]
        )

    # Print Summary of download run
    # 打印本次下载运行的汇总信息
    print(f"\n完成，失败 {len(failed)} 家：{[t for t,_ in failed]}")
    counts = con.execute("""
        SELECT 'income'   AS tbl, count(*) AS rows FROM income   UNION ALL
        SELECT 'balance',          count(*)         FROM balance  UNION ALL
        SELECT 'cashflow',         count(*)         FROM cashflow
    """).df()
    print("\n数据库行数：")
    print(counts.to_string(index=False))
    con.close()

if __name__ == "__main__":
    main()
