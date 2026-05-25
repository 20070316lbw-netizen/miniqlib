# ==============================================================================
# ABSOLUTE FILE PATH: C:\Users\liu\Desktop\miniqlib\mini_qlib\fetcher\fetch_edgar.py
# DESCRIPTION: Core low-level module for SEC EDGAR financial data fetching and DuckDB loading.
# 描述: 用于从 SEC EDGAR 抓取财务数据并加载到 DuckDB 的核心底层模块。
# WARNING: This is a critical core file. Do NOT modify its path or behavior carelessly.
# 警告: 这是一个关键的核心文件。切勿随意修改其路径或行为。
# ==============================================================================

import requests
import pandas as pd
import duckdb
import time
from pathlib import Path

# ── DEFAULT CONFIG / 默认配置 ──────────────────────────────────────────────────

INCOME_CONCEPTS = {
    "revenue":      ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "gross_profit": ["GrossProfit"],
    "op_income":    ["OperatingIncomeLoss"],
    "net_income":   ["NetIncomeLoss"],
    "eps_diluted":  ["EarningsPerShareDiluted"],
}

BALANCE_CONCEPTS = {
    "total_assets":       ["Assets"],
    "total_liabilities":  ["Liabilities"],
    "equity":             ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "cash":               ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsAndShortTermInvestments"],
    "total_debt":         ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligation"],
}

CASHFLOW_CONCEPTS = {
    "cfo":        ["NetCashProvidedByUsedInOperatingActivities"],
    "capex":      ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "fcf_direct": ["FreeCashFlow"],
}


# ── SEC EDGAR API FUNCTIONS / SEC EDGAR API 函数 ───────────────────────────────

def get_cik_map(headers: dict, verify: bool = True) -> dict:
    """
    Fetch the complete mapping of tickers to CIKs from SEC EDGAR.
    从 SEC EDGAR 获取完整的股票代码（Ticker）到 CIK 的映射表。
    """
    url = "https://www.sec.gov/files/company_tickers.json"
    resp = requests.get(url, headers=headers, timeout=30, verify=verify)
    if resp.status_code == 200:
        return {
            v["ticker"].upper(): str(v["cik_str"]).zfill(10)
            for v in resp.json().values()
        }
    else:
        raise ConnectionError(f"Failed to fetch CIK mapping from SEC. HTTP Status: {resp.status_code}")


def fetch_company_facts(cik: str, headers: dict, verify: bool = True) -> dict | None:
    """
    Fetch all XBRL facts for a given company CIK from SEC EDGAR API.
    从 SEC EDGAR API 获取指定公司 CIK 的所有原始 XBRL 事实数据。
    """
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    try:
        resp = requests.get(url, headers=headers, timeout=30, verify=verify)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


# ── XBRL FACTS PARSING FUNCTIONS / XBRL 事实数据解析函数 ───────────────────────────

def extract_concept(facts: dict, concepts: list) -> list:
    """
    Extract a single concept by order of priority, returning historical records.
    按优先级顺序提取单个财务概念，返回历史记录列表。
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    results = {}
    for concept in concepts:
        if concept not in us_gaap:
            continue
        units = us_gaap[concept].get("units", {})
        rows = units.get("USD", units.get("shares", []))
        for r in rows:
            if r.get("form") not in ("10-K", "10-Q", "10-K/A", "10-Q/A"):
                continue
            key = (r.get("end"), r.get("filed"), r.get("form"))
            if key not in results:
                results[key] = {
                    "period_end": r.get("end"),
                    "filed":      r.get("filed"),
                    "value":      r.get("val"),
                    "form":       r.get("form"),
                }
    return list(results.values())


def facts_to_df(facts: dict, concept_map: dict, ticker: str) -> pd.DataFrame:
    """
    Extract multiple concepts and pivot them into a point-in-time DataFrame.
    提取多个财务概念并将其透视为 point-in-time（时点）格式的 DataFrame。
    """
    all_records = {}

    for col_name, concepts in concept_map.items():
        for row in extract_concept(facts, concepts):
            key = (row["period_end"], row["filed"], row["form"])
            if key not in all_records:
                all_records[key] = {
                    "ticker":     ticker,
                    "period_end": row["period_end"],
                    "filed":      row["filed"],
                    "form":       row["form"],
                }
            if col_name not in all_records[key]:
                all_records[key][col_name] = row["value"]

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(list(all_records.values()))
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["filed"]      = pd.to_datetime(df["filed"])
    return df.sort_values(["period_end", "filed"]).reset_index(drop=True)


# ── DUCKDB DATABASE FUNCTIONS / DUCKDB 数据库函数 ───────────────────────────────

def init_db(con):
    """
    Initialize the database schemas for financial statements and logs.
    初始化财务报表和下载日志的数据库表结构。
    """
    con.execute("""
        CREATE TABLE IF NOT EXISTS income (
            ticker       VARCHAR,
            period_end   DATE,
            filed        DATE,
            form         VARCHAR,
            revenue      DOUBLE,
            gross_profit DOUBLE,
            op_income    DOUBLE,
            net_income   DOUBLE,
            eps_diluted  DOUBLE
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS balance (
            ticker            VARCHAR,
            period_end        DATE,
            filed             DATE,
            form              VARCHAR,
            total_assets      DOUBLE,
            total_liabilities DOUBLE,
            equity            DOUBLE,
            cash              DOUBLE,
            total_debt        DOUBLE
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS cashflow (
            ticker      VARCHAR,
            period_end  DATE,
            filed       DATE,
            form        VARCHAR,
            cfo         DOUBLE,
            capex       DOUBLE,
            fcf_direct  DOUBLE
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS download_log (
            ticker     VARCHAR PRIMARY KEY,
            status     VARCHAR,
            updated_at TIMESTAMP DEFAULT current_timestamp
        )
    """)


def already_done(con, ticker: str) -> bool:
    """
    Check if a company ticker has been successfully downloaded.
    检查某只股票代码是否已经成功下载完成。
    """
    r = con.execute("SELECT status FROM download_log WHERE ticker=?", [ticker]).fetchone()
    return r is not None and r[0] == "ok"


def save_df(con, table: str, df: pd.DataFrame):
    """
    Save DataFrame into target DuckDB table, ensuring schema alignment.
    将 DataFrame 保存至目标 DuckDB 表中，确保表结构完全对齐。
    """
    if df.empty:
        return
    table_cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
    for col in table_cols:
        if col not in df.columns:
            df[col] = None
    df = df[table_cols]
    con.register("_tmp", df)
    con.execute(f"INSERT INTO {table} SELECT * FROM _tmp")
    con.unregister("_tmp")
