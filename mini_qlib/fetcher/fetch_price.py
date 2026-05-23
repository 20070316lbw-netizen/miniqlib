"""
批量拉取股票池的历史行情数据

修复说明（针对静默丢票问题）：
  旧版 batch_size=50 + 10 年跨度会触发 Yahoo 限流，批内部分票返回全 NaN，
  但 yf.download 不抛异常，最后 dropna 把它们默默删掉，还显示 ✅ 成功。
  新版做三件事：
    1) 缩小 batch_size、批间 sleep —— 从源头降低触发限流概率
    2) 每批拉完主动对比"请求 vs 实际拿到"，揪出缺失的票，不再静默
    3) 对缺失的票自动重试若干轮，最后仍缺的明确列出来报警
"""
import time

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta


def _download_one_batch(batch, start_date, end_date):
    """
    拉一批，返回 (长格式DataFrame 或 None, 实际成功拿到的 ticker 集合)。

    关键点：yf.download 批量请求时，失败的票是"列全 NaN"而不是抛异常。
    所以不能只靠 try/except，必须拉完后看实际有哪些票真有数据。
    """
    try:
        data = yf.download(
            batch,
            start=start_date,
            end=end_date,
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        print(f"    整批请求异常: {e}")
        return None, set()

    if data is None or data.empty:
        return None, set()

    # 单票时 yfinance 返回的列是单层 Index，没有 ticker 这一层，
    # 需要手动补一个 ticker 维度，否则 stack(level=1) 会报错。
    # （这正是之前标记过的 MultiIndex 对齐风险点）
    if not isinstance(data.columns, pd.MultiIndex):
        only = batch[0] if len(batch) == 1 else "UNKNOWN"
        data.columns = pd.MultiIndex.from_product([data.columns, [only]])

    data_long = data.stack(level=1, future_stack=True).reset_index()
    data_long.columns = [c.lower() for c in data_long.columns]

    # 丢掉 close 为 NaN 的行（还没上市 / 当天无数据 / 限流返回空）
    data_long = data_long.dropna(subset=["close"])

    if data_long.empty:
        return None, set()

    got = set(data_long["ticker"].unique())
    return data_long, got


def fetch_prices_batch(tickers, start_date, end_date,
                        batch_size=20, sleep_between=1.5,
                        max_retry_rounds=3):
    """
    分批拉取多只股票的历史日线数据（带失败检测和自动重试）。

    参数:
        tickers: 股票代码列表
        start_date / end_date: 'YYYY-MM-DD'
        batch_size: 每批多少只（默认 20，比旧版 50 小，避免限流）
        sleep_between: 每批之间停几秒（默认 1.5，给 Yahoo 喘息）
        max_retry_rounds: 对缺失票最多重试几轮（默认 3）

    返回:
        长格式 DataFrame: date, ticker, open, high, low, close, volume
    """
    all_data = []
    requested = list(tickers)          # 一开始想要的全部
    got_total = set()                  # 累计已经成功拿到的

    def run_pass(ticker_list, label, bsize):
        """跑一遍：把 ticker_list 按 bsize 分批拉，结果塞进 all_data，更新 got_total"""
        total_batches = (len(ticker_list) + bsize - 1) // bsize
        for i in range(0, len(ticker_list), bsize):
            batch = ticker_list[i:i + bsize]
            bn = i // bsize + 1
            print(f"[{label}] 第 {bn}/{total_batches} 批 ({len(batch)} 只)...")

            df_batch, got = _download_one_batch(batch, start_date, end_date)

            missing_in_batch = set(batch) - got
            if df_batch is not None:
                all_data.append(df_batch)
                got_total.update(got)

            if missing_in_batch:
                # 这一批里没拿到的票，明确报出来——不再静默
                print(f"  ⚠️ 本批 {len(got)}/{len(batch)} 成功，"
                      f"缺: {sorted(missing_in_batch)}")
            else:
                print(f"  ✅ 本批 {len(batch)} 只全部成功")

            time.sleep(sleep_between)

    # ---- 第一轮：正常批量拉 ----
    run_pass(requested, "主拉取", batch_size)

    # ---- 后续几轮：只重试还缺的票，批量更小，停顿更久 ----
    for r in range(1, max_retry_rounds + 1):
        missing = [t for t in requested if t not in got_total]
        if not missing:
            break
        print(f"\n=== 第 {r} 轮重试，仍缺 {len(missing)} 只: {sorted(missing)} ===")
        # 重试时批量减半，进一步降限流概率
        run_pass(missing, f"重试{r}",
                 max(1, batch_size // 2 ** r))

    if not all_data:
        print("一条数据都没拉到")
        return pd.DataFrame()

    result = pd.concat(all_data, ignore_index=True)
    result = result.dropna(subset=["close"])
    result = result[["date", "ticker", "open", "high", "low",
                      "close", "volume"]]

    # ---- 最终对账：明确告诉你库里到底缺不缺、缺谁 ----
    final_missing = sorted(set(requested) - set(result["ticker"].unique()))
    print("\n" + "=" * 55)
    print(f"请求 {len(requested)} 只，最终拿到 "
          f"{result['ticker'].nunique()} 只")
    if final_missing:
        print(f"❌ 重试后仍缺 {len(final_missing)} 只: {final_missing}")
        print("   这些票没进库，需要单独处理（不要假装成功）")
    else:
        print("✅ 全部股票都成功拿到，无遗漏")
    print("=" * 55)

    return result


if __name__ == "__main__":
    # 测试一下:先拉 5 只股票看看
    test_tickers = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN']

    end_date = datetime.today().strftime('%Y-%m-%d')
    start_date = (datetime.today() - timedelta(days=365)).strftime('%Y-%m-%d')

    print(f"拉取范围: {start_date} 到 {end_date}")
    print(f"测试股票: {test_tickers}\n")

    df = fetch_prices_batch(test_tickers, start_date, end_date)

    print(f"\n总共拉到 {len(df)} 行")
    print("\n前 10 行:")
    print(df.head(10))
    print("\n每只股票的数据量:")
    print(df['ticker'].value_counts())