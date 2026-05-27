"""
Executable script for incremental price data scraping and replenishment.
用于增量价格数据抓取和补充新数据的可执行脚本。
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Fix Windows console emoji printing error
# 修复 Windows 控制台下 Emoji 打印可能出现的编码错误
try:
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, OSError):
    pass  # stdout may be redirected or not support reconfigure

# Add project root to sys.path to enable clean absolute imports
# 将项目根目录添加到 sys.path 以支持干净的绝对导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fetcher.fetch_price import fetch_prices_batch
from fetcher.get_sp_500_list import get_sp500_tickers
from data.load_data import init_prices_table, insert_prices, get_latest_price_date
from utils.config import get_price_db


def fetch_and_supplement_prices(tickers: list[str], overlap_days: int = 5, force_full: bool = False) -> int:
    """
    Incremental fetch and merge prices.
    增量拉取并合并价格数据到数据库中。
    
    Parameters:
        tickers: List of stock symbols to scrape / 股票代码列表
        overlap_days: Number of days to overlap to prevent missing weekend/timezone data / 重叠天数，避免遗漏周末或时区差数据
        force_full: If True, ignore existing data and fetch full 10-year history / 是否强制拉取完整10年历史数据
    """
    end_date = datetime.today().strftime('%Y-%m-%d')
    
    # 1. Determine start date
    latest_date_str = None if force_full else get_latest_price_date()
    
    if latest_date_str:
        # Incremental mode: fetch from latest date minus overlap_days
        # 增量模式：从最新日期减去重叠天数开始拉取
        latest_date = datetime.strptime(latest_date_str, '%Y-%m-%d')
        start_date = (latest_date - timedelta(days=overlap_days)).strftime('%Y-%m-%d')
        print(f"检测到已有历史数据，最新日期为: {latest_date_str}")
        print(f"🚀 启动【增量补充】模式：抓取范围 {start_date} 至 {end_date} (重叠 {overlap_days} 天)")
    else:
        # Full mode: fetch last 10 years
        # 完整模式：拉取过去10年的完整历史数据
        start_date = (datetime.today() - timedelta(days=3650)).strftime('%Y-%m-%d')
        print(f"数据库中未检测到历史数据，或指定了强制完整拉取。")
        print(f"🚀 启动【完整拉取】模式：抓取范围 {start_date} 至 {end_date} (过去 10 年)")

    print(f"目标股票数量: {len(tickers)} 只\n")

    # 2. Fetch prices using robust batch fetcher
    df = fetch_prices_batch(tickers, start_date, end_date)
    if df.empty:
        print("⚠️ 未拉取到任何新的行情数据，写入中止。")
        return 0

    print(f"\n📦 成功拉取到 {len(df)} 行行情数据")

    # 3. Securely insert or replace into database (use write mode for price DB)
    # 安全地插入或替换到数据库中（使用写模式打开行情数据库）
    with get_price_db(read_only=False) as con:
        init_prices_table(con)
        written_rows = insert_prices(con, df)
        print(f"✅ 行情增量写入完成，受影响/更新的数据库行数: {written_rows} 行")
        return written_rows


def main() -> None:
    # Get active S&P 500 tickers
    # 获取标普 500 成分股列表
    print("获取 S&P 500 最新成分股列表...")
    try:
        sp500 = get_sp500_tickers()
        tickers = sp500['symbol'].tolist()
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        sys.exit(1)

    # Perform the incremental fetch
    # 执行增量抓取和数据补充
    fetch_and_supplement_prices(tickers)


if __name__ == "__main__":
    main()
