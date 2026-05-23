# ==============================================================================
# ABSOLUTE FILE PATH: C:\Users\liu\Desktop\miniqlib\mini_qlib\fetcher\get_sp_500_list.py
# DESCRIPTION: Module to fetch and cache the S&P 500 company list from Wikipedia.
# 描述: 从维基百科获取并缓存标普500成分股列表的模块。
# WARNING: This file is critical for standard ticker alignment. Do NOT modify carelessly.
# 警告: 本文件对于标准的股票代码对齐至关重要。切勿随意修改。
# ==============================================================================

import time
from io import StringIO
from pathlib import Path
import pandas as pd
import requests

# Cache file location: under database/ directory
# 缓存文件位置：database/ 目录下
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = PROJECT_ROOT / "database" / "sp500_tickers.csv"

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def _fetch_from_wikipedia(max_retries: int = 3) -> pd.DataFrame:
    """
    Fetch S&P 500 tickers from Wikipedia with retry mechanism.
    从维基百科抓取标普500成分股名单，带重试机制。
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            print(f"  正在抓取维基百科成分股名单（第 {attempt}/{max_retries} 次）...")
            response = requests.get(WIKI_URL, headers=headers, timeout=(10, 30))
            response.raise_for_status()

            tables = pd.read_html(StringIO(response.text))
            sp500 = tables[0]

            sp500 = sp500.rename(columns={
                'Symbol': 'symbol',
                'Security': 'security',
                'GICS Sector': 'sector',
                'GICS Sub-Industry': 'sub_industry',
            })
            sp500 = sp500[['symbol', 'security', 'sector', 'sub_industry']]

            # Convert BRK.B to BRK-B format for yfinance compatibility
            # 将 BRK.B 格式转换为 BRK-B 格式以适配 yfinance
            sp500['symbol'] = sp500['symbol'].str.replace('.', '-', regex=False)

            print(f"  ✅ 抓取成功，共 {len(sp500)} 只")
            return sp500

        except Exception as e:
            last_err = e
            print(f"  ⚠️ 第 {attempt} 次失败: {type(e).__name__}")
            if attempt < max_retries:
                wait = attempt * 3   # Incremental backoff / 递增退避
                print(f"     {wait} 秒后重试...")
                time.sleep(wait)

    raise RuntimeError(f"维基百科抓取 {max_retries} 次均失败") from last_err


def get_sp500_tickers(force_refresh: bool = False) -> pd.DataFrame:
    """
    Return S&P 500 tickers DataFrame: symbol, security, sector, sub_industry
    返回标普500成分股 DataFrame 列表。

    Parameters
    ----------
    参数
    ----------
    force_refresh: bool
        If True, ignore cache and force fetch from Wikipedia.
        若为 True，忽略缓存强制重新抓取覆盖。
    """
    # ---- 1st Layer: Cache Priority / 第一层：缓存优先 ----
    if CACHE_PATH.exists() and not force_refresh:
        df = pd.read_csv(CACHE_PATH, encoding="utf-8")
        print(f"📂 使用本地缓存名单: {CACHE_PATH}")
        print(f"   共 {len(df)} 只（如需更新: get_sp500_tickers(force_refresh=True)）")
        return df

    # ---- 2nd Layer: Wikipedia Scrape / 第二层：缓存没有或强制刷新，去抓 ----
    try:
        df = _fetch_from_wikipedia()
        # Save cache immediately upon successful fetch
        # 抓取成功后立即写入缓存文件，确保下次运行秒级加载
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(CACHE_PATH, index=False, encoding="utf-8")
        print(f"💾 已写入缓存: {CACHE_PATH}")
        print("   以后默认读这份，不再依赖维基百科")
        return df

    # ---- 3rd Layer: Scrape Failure Rescue / 第三层：抓取失败给出补救提示 ----
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ 缓存不存在，且维基百科抓取失败。")
        print(f"   原因: {e}")
        print("-" * 60)
        print("手动补救（任选其一）：")
        print(f"  1) 换个网络/挂代理后，单独跑一次本文件生成缓存：")
        print(f"     uv run python -m fetcher.get_sp500_list")
        print(f"  2) 找一份 S&P 500 成分股 CSV，确保至少有 symbol 列，")
        print(f"     存到: {CACHE_PATH}")
        print(f"     （symbol 里 BRK.B 这类要写成 BRK-B）")
        print("=" * 60)
        raise


if __name__ == "__main__":
    df = get_sp500_tickers()
    print(f"\n成功拿到 {len(df)} 只股票")
    print("\n前 10 只:")
    print(df.head(10))
    print("\n按行业分布:")
    print(df['sector'].value_counts())