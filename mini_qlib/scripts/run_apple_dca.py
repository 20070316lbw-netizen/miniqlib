# -*- coding: utf-8 -*-
"""
MiniQLib Config-driven DCA Backtesting and Benchmarking Script.
Loads DCA configurations, runs the DCA Apple strategy, and compares it side-by-side with S&P 500.
"""
import os
import sys
import yaml
import numpy as np
import pandas as pd
from pathlib import Path
import logging

# Ensure stdout handles encoding nicely
try:
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, OSError):
    pass

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "mini_qlib"))

from mini_qlib.data.load_data import read_prices
from mini_qlib.backtest.backtest import run_backtest
from mini_qlib.backtest.strategy import AppleDCAStrategy
from mini_qlib.backtest.data_portal import DataPortal
from mini_qlib.utils.log import configure_root, get_logger

_log = get_logger(__name__)


def load_config(config_path: Path) -> dict:
    """Read YAML configuration file"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def calculate_metrics(nav_series: pd.Series) -> dict:
    """Calculate core performance metrics for a NAV series"""
    daily_returns = nav_series.pct_change().dropna()
    total_return = (nav_series.iloc[-1] / nav_series.iloc[0]) - 1.0
    n_days = len(nav_series)

    # Annualized Return (assuming 252 trading days per year)
    annualized_return = (1.0 + total_return) ** (252.0 / n_days) - 1.0 if n_days > 0 else 0.0

    # Sharpe Ratio (no-risk rate assumed as 0.0)
    sharpe_ratio = np.sqrt(252.0) * (daily_returns.mean() / daily_returns.std()) if daily_returns.std() > 0 else 0.0

    # Max Drawdown
    cum_max = nav_series.cummax()
    drawdowns = (cum_max - nav_series) / cum_max
    max_drawdown = drawdowns.max()

    return {
        "total_return": total_return,
        "ann_return": annualized_return,
        "sharpe": sharpe_ratio,
        "max_dd": max_drawdown,
        "final_nav": nav_series.iloc[-1]
    }


def main():
    configure_root(level=logging.INFO)
    print("=" * 75)
    print("🚀 MiniQLib 定投对标回测启动 / Config-driven DCA Backtest & Benchmarking")
    print("=" * 75)

    # 1. Load DCA configuration
    config_file = PROJECT_ROOT / "config_dca.yaml"
    if not config_file.exists():
        _log.error("❌ 配置文件不存在: %s", config_file)
        sys.exit(1)

    print(f"📂 加载定投策略配置文件: {config_file}")
    config = load_config(config_file)

    # 2. Read pricing data from DuckDB
    print("💽 正在从行情数据库中加载历史价格数据...")
    raw_df = read_prices()
    if raw_df.empty:
        _log.error("❌ 行情数据库为空，请运行 scripts/fetch_data.py 下载数据。")
        sys.exit(1)

    raw_df["date"] = pd.to_datetime(raw_df["date"])
    df = raw_df.set_index(["date", "ticker"]).sort_index()

    # 3. Filter data by date range
    backtest_conf = config["backtest"]
    start_date = pd.Timestamp(backtest_conf.get("start_date", "2008-01-01"))
    end_date = pd.Timestamp(backtest_conf.get("end_date", "2026-05-30"))

    dt = df.index.get_level_values("date")
    df_sliced = df.loc[(dt >= start_date) & (dt <= end_date)]

    # 4. Instantiate strategy dynamically from YAML
    strat_conf = config["strategy"]
    strat_class = strat_conf["class"]
    strat_params = strat_conf["params"]

    print(f"🏗️ 实例化定投策略: {strat_class}")
    print(f"   [参数配置] Ticker: {strat_params['ticker']} | 额度: {strat_params['dca_amount']} "
          f"| 是否按股数: {strat_params['is_shares']}")

    # ── 布尔值类型安全校验 ──────────────────────────────────────────
    # YAML 中 is_shares: false（无引号）→ Python bool False ✅
    # YAML 中 is_shares: "false"（有引号）→ Python str "false" → bool("false") = True ❌
    # 此处显式校验类型，防止用户手误加引号导致行为反转。
    is_shares_raw = strat_params.get("is_shares", True)
    if not isinstance(is_shares_raw, bool):
        _log.warning("⚠️ is_shares 应为布尔值 (true/false)，当前类型为 %s，值=%s。"
                     "已强制转为 True。请检查 config_dca.yaml 中 is_shares 是否被加了引号。", type(is_shares_raw).__name__, repr(is_shares_raw))

    if strat_class == "AppleDCAStrategy":
        is_shares = bool(is_shares_raw)  # 已经过类型警告，此处安全
        strategy = AppleDCAStrategy(
            ticker=strat_params.get("ticker", "AAPL"),
            dca_amount=float(strat_params.get("dca_amount", 10.0)),
            is_shares=is_shares
        )
    else:
        _log.error("❌ 未知策略类: %s", strat_class)
        sys.exit(1)

    # 5. Run the high-fidelity backtest
    print("\n🏁 正在运行定投策略高保真回测 (Event-driven backtesting)...")
    backtest_result = run_backtest(
        df=df_sliced,
        predictions=None,
        initial_cash=float(backtest_conf.get("initial_cash", 100000.0)),
        max_volume_ratio=float(backtest_conf.get("max_volume_ratio", 0.1)),
        slippage=float(backtest_conf.get("slippage", 0.0005)),
        fee_rate=float(backtest_conf.get("fee_rate", 0.0003)),
        tax_rate=float(backtest_conf.get("tax_rate", 0.001)),
        strategy=strategy
    )

    # 6. Calculate benchmark performance (S&P 500 Index / ETF Buy-and-Hold)
    benchmark_ticker = backtest_conf.get("benchmark_ticker", "SPY")
    print(f"\n📊 正在计算对比基准 {benchmark_ticker} (标普 500) 的买入持有业绩...")

    data_portal = DataPortal(df_sliced)
    backtest_dates = backtest_result.index.sort_values()
    start_day = backtest_dates[0]
    initial_cash = float(backtest_conf.get("initial_cash", 100000.0))

    # Get first day's price to calculate initial share count for S&P 500 B&H
    bench_price = data_portal.get_current(benchmark_ticker, "open", start_day)
    if pd.isna(bench_price) or bench_price <= 0.0:
        bench_price = data_portal.get_current(benchmark_ticker, "close", start_day)

    bench_shares = initial_cash / bench_price
    bench_nav_records = []

    for curr_date in backtest_dates:
        close_p = data_portal.get_current(benchmark_ticker, "close", curr_date)
        if pd.isna(close_p) or close_p <= 0.0:
            close_p = bench_price  # Safe fallback
        bench_nav_records.append({
            "date": curr_date,
            "nav": bench_shares * close_p
        })

    bench_result = pd.DataFrame(bench_nav_records).set_index("date")

    # 7. Print side-by-side performance comparison
    strat_metrics = calculate_metrics(backtest_result["nav"])
    bench_metrics = calculate_metrics(bench_result["nav"])

    print("\n" + "=" * 75)
    print("📈 MiniQLib 定投对标业绩双侧对照表 (DCA vs. Benchmark Report)")
    print("=" * 75)
    print(f"   回测时间范围 (Period):    {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
    print(f"   总交易天数 (Total Days):   {len(backtest_dates)} 个交易日")
    print("-" * 75)
    print(f"   [理财指标 / Metrics]        定投策略 (AAPL DCA)     标普500持有 ({benchmark_ticker} B&H)")
    print(f"   --------------------        ------------------     --------------------")
    print(f"   初始现金 (Start Capital)    {initial_cash:,.2f} USD         {initial_cash:,.2f} USD")
    print(f"   期末资产 (Final NAV)        {strat_metrics['final_nav']:,.2f} USD         {bench_metrics['final_nav']:,.2f} USD")
    print(f"   累计收益 (Total Return)     {strat_metrics['total_return']*100:15.4f}%     {bench_metrics['total_return']*100:18.4f}%")
    print(f"   年化收益 (Ann Return)       {strat_metrics['ann_return']*100:15.4f}%     {bench_metrics['ann_return']*100:18.4f}%")
    print(f"   年化夏普 (Sharpe Ratio)     {strat_metrics['sharpe']:15.4f}      {bench_metrics['sharpe']:18.4f}")
    print(f"\n   ℹ️ 注：定投策略含 T+1 撮合延迟、{backtest_conf.get('slippage', 0.0005)*100:.3f}% 滑点、{backtest_conf.get('fee_rate', 0.0003)*100:.3f}% 手续费；"
          f"\n      标杆 (SPY B&H) 为首日开盘全仓买入、零交易成本。两者执行模型不同，")
    print(f"      摩擦成本已包含在定投收益差异中，不代表纯 alpha。")
    print(f"   最大回撤 (Max Drawdown)     {strat_metrics['max_dd']*100:15.4f}%     {bench_metrics['max_dd']*100:18.4f}%")
    print("=" * 75)
    print("🎉 定投对比回测运行圆满完成！")


if __name__ == "__main__":
    main()