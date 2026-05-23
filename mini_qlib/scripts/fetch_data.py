"""
用于抓取数据
"""
import sys
from pathlib import Path

# Fix Windows console emoji printing error
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timedelta

from fetcher.fetch_price import fetch_prices_batch
from fetcher.get_sp_500_list import get_sp500_tickers
from data.load_data import load_prices

# 第一步：拉 S&P 500 列表
sp500 = get_sp500_tickers()
tickers = sp500['symbol'].tolist()

end_date = datetime.today().strftime('%Y-%m-%d')
start_date = (datetime.today() - timedelta(days=3650)).strftime('%Y-%m-%d')

print(f"=== 拉取范围: {start_date} 到 {end_date} ===")
print(f"共 {len(tickers)} 只股票\n")

# 第二步：拉价格数据
df = fetch_prices_batch(tickers, start_date, end_date)
print(f"\n📦 拉到 {len(df)} 行数据\n")

# 第三步：写入数据库
count = load_prices(df)
print(f"✅ 写入完成，共 {count} 行")
