"""
拉取标普500成分股列表

策略（缓存优先，解决两个问题）：
  问题1: 维基百科 SSL 偶发中断，每次实时抓不可靠
  问题2: 成分股每季度变动，每次实时抓会导致回测无法复现
          + 用今天的名单回测过去 = 幸存者偏差（已知妥协，先跑通）

三层逻辑:
  1) 本地缓存存在 -> 直接读，不碰网络（常态路径，快/稳/可复现）
  2) 缓存不存在 -> 抓维基百科（带重试），成功后立刻写缓存
  3) 抓取也失败 -> 不崩溃，打印手动补救指引

⚠️ 幸存者偏差说明：这份名单是"抓取当天"的 S&P 500 成分股。
   用它回测历史，相当于假设这些公司过去就一直在指数里，
   且忽略了期间被剔除/退市的公司。作为学习项目第一版可接受，
   将来做严肃回测时需换成"历史成分股"数据。
"""
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

# 缓存文件位置：database/ 目录下
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = PROJECT_ROOT / "database" / "sp500_tickers.csv"

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def _fetch_from_wikipedia(max_retries: int = 3) -> pd.DataFrame:
    """从维基百科抓成分股，带重试。全部失败则抛异常。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            print(f"  正在抓取维基百科成分股名单（第 {attempt}/{max_retries} 次）...")
            # timeout=(连接超时, 读取超时)，给慢/不稳的网络更多余地
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

            # yfinance 不认 BRK.B 这种点号，要改成 BRK-B
            sp500['symbol'] = sp500['symbol'].str.replace('.', '-', regex=False)

            print(f"  ✅ 抓取成功，共 {len(sp500)} 只")
            return sp500

        except Exception as e:
            last_err = e
            print(f"  ⚠️ 第 {attempt} 次失败: {type(e).__name__}")
            if attempt < max_retries:
                wait = attempt * 3   # 3s, 6s, ... 递增退避
                print(f"     {wait} 秒后重试...")
                time.sleep(wait)

    raise RuntimeError(f"维基百科抓取 {max_retries} 次均失败") from last_err


def get_sp500_tickers(force_refresh: bool = False) -> pd.DataFrame:
    """
    返回 S&P 500 成分股 DataFrame: symbol, security, sector, sub_industry

    参数:
        force_refresh: True 时忽略缓存，强制重新抓取并覆盖缓存
                       （想更新名单时用，平时不要开）

    逻辑: 缓存优先 -> 抓取 -> 兜底指引
    """
    # ---- 第一层：缓存优先 ----
    if CACHE_PATH.exists() and not force_refresh:
        df = pd.read_csv(CACHE_PATH)
        print(f"📂 使用本地缓存名单: {CACHE_PATH}")
        print(f"   共 {len(df)} 只（如需更新: get_sp500_tickers(force_refresh=True)）")
        return df

    # ---- 第二层：缓存没有（或强制刷新），去抓 ----
    try:
        df = _fetch_from_wikipedia()
        # 抓成功立刻写缓存，下次就走第一层
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(CACHE_PATH, index=False)
        print(f"💾 已写入缓存: {CACHE_PATH}")
        print("   以后默认读这份，不再依赖维基百科")
        return df

    # ---- 第三层：抓取也失败，给手动补救指引，不崩溃 ----
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
    # 直接跑本文件 = 测试 / 首次生成缓存
    df = get_sp500_tickers()
    print(f"\n成功拿到 {len(df)} 只股票")
    print("\n前 10 只:")
    print(df.head(10))
    print("\n按行业分布:")
    print(df['sector'].value_counts())