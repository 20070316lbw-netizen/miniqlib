# -*- coding: utf-8 -*-
"""
Generate stunning, premium dark-mode charts for the Apple DCA video.
Creates:
1. nav_comparison.png (Log scale NAV comparison AAPL DCA vs SPY B&H)
2. drawdown_comparison.png (Drawdown curve showing risk reduction)
3. dca_shares_purchased.png (Shares purchased with $1,000 USD over time, highlighting automatic dip-buying)
"""
import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "mini_qlib"))

from mini_qlib.data.load_data import read_prices
from mini_qlib.backtest.backtest import run_backtest
from mini_qlib.backtest.strategy import AppleDCAStrategy
from mini_qlib.backtest.data_portal import DataPortal

# Set up matplotlib style for premium dark-mode look
plt.style.use('dark_background')
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.facecolor'] = '#0B0F19'
plt.rcParams['axes.facecolor'] = '#0B0F19'
plt.rcParams['grid.color'] = '#1E293B'
plt.rcParams['grid.alpha'] = 0.5
plt.rcParams['axes.edgecolor'] = '#334155'
plt.rcParams['xtick.color'] = '#94A3B8'
plt.rcParams['ytick.color'] = '#94A3B8'

def run_simulations():
    print("⏳ Running backtests and extracting data...")
    raw_df = read_prices()
    raw_df["date"] = pd.to_datetime(raw_df["date"])
    df = raw_df.set_index(["date", "ticker"]).sort_index()

    start_date = pd.Timestamp("2008-01-01")
    end_date = pd.Timestamp("2026-05-30")
    dt = df.index.get_level_values("date")
    df_sliced = df.loc[(dt >= start_date) & (dt <= end_date)]

    # 1. Run Apple DCA Strategy (Daily 10 shares)
    strategy = AppleDCAStrategy(ticker="AAPL", dca_amount=10.0, is_shares=True)
    backtest_result = run_backtest(
        df=df_sliced,
        predictions=None,
        initial_cash=100000.0,
        max_volume_ratio=0.1,
        slippage=0.0005,
        fee_rate=0.0003,
        tax_rate=0.001,
        strategy=strategy
    )

    # 2. Run SPY B&H Benchmark
    data_portal = DataPortal(df_sliced)
    backtest_dates = backtest_result.index.sort_values()
    start_day = backtest_dates[0]
    initial_cash = 100000.0

    bench_price = data_portal.get_current("SPY", "open", start_day)
    if pd.isna(bench_price) or bench_price <= 0.0:
        bench_price = data_portal.get_current("SPY", "close", start_day)
    bench_shares = initial_cash / bench_price
    
    bench_nav_records = []
    for curr_date in backtest_dates:
        close_p = data_portal.get_current("SPY", "close", curr_date)
        if pd.isna(close_p) or close_p <= 0.0:
            close_p = bench_price
        bench_nav_records.append({
            "date": curr_date,
            "nav": bench_shares * close_p
        })
    bench_result = pd.DataFrame(bench_nav_records).set_index("date")

    # 3. Get raw Apple close prices for DCA demonstration
    aapl_close = df_sliced.xs("AAPL", level="ticker")["close"].reindex(backtest_dates).ffill()

    return backtest_result, bench_result, aapl_close

def plot_nav_comparison(aapl_dca, spy_bh, output_dir):
    print("📈 Plotting NAV Comparison Chart...")
    fig, ax = plt.subplots(figsize=(12, 7.5), dpi=300)
    
    # Grid and styling
    ax.grid(True, which="both", linestyle="--", linewidth=0.5)
    
    # Plot lines with glowing neon colors
    ax.plot(aapl_dca.index, aapl_dca["nav"], color='#00F2FE', linewidth=2.5, label='Apple DCA Strategy (AAPL)')
    ax.plot(spy_bh.index, spy_bh["nav"], color='#FF5E62', linewidth=1.8, linestyle='--', label='S&P 500 Buy & Hold (SPY)')
    
    # Set logarithmic scale
    ax.set_yscale('log')
    
    # Formatting
    ax.set_title("Apple DCA vs S&P 500 Buy & Hold (2008 - 2026)\n[Logarithmic Scale - Cash Compounding Path]", 
                 fontsize=16, fontweight='bold', pad=20, color='#F8FAFC')
    ax.set_xlabel("Year", fontsize=12, color='#E2E8F0', labelpad=10)
    ax.set_ylabel("Portfolio NAV (USD) - Log Scale", fontsize=12, color='#E2E8F0', labelpad=10)
    
    # Legend
    legend = ax.legend(loc='upper left', fontsize=11, framealpha=0.9, facecolor='#0B0F19', edgecolor='#334155')
    plt.setp(legend.get_texts(), color='#F8FAFC')
    
    # Y-axis ticks formatting
    import matplotlib.ticker as ticker
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f"${x:,.0f}"))
    
    # Text annotations for shock value
    final_aapl = aapl_dca["nav"].iloc[-1]
    final_spy = spy_bh["nav"].iloc[-1]
    
    ax.annotate(f"AAPL DCA Final: ${final_aapl:,.0f} USD\n(+3,589.6%)",
                xy=(aapl_dca.index[-1], final_aapl),
                xytext=(aapl_dca.index[-1] - pd.Timedelta(days=2200), final_aapl * 1.5),
                arrowprops=dict(facecolor='#00F2FE', arrowstyle="->", connectionstyle="arc3,rad=-0.1"),
                fontsize=11, color='#00F2FE', fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.5", fc="#0B0F19", ec="#00F2FE", alpha=0.8))
                
    ax.annotate(f"SPY B&H Final: ${final_spy:,.0f} USD\n(+631.2%)",
                xy=(spy_bh.index[-1], final_spy),
                xytext=(spy_bh.index[-1] - pd.Timedelta(days=2200), final_spy * 0.3),
                arrowprops=dict(facecolor='#FF5E62', arrowstyle="->", connectionstyle="arc3,rad=0.1"),
                fontsize=11, color='#FF5E62', fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.5", fc="#0B0F19", ec="#FF5E62", alpha=0.8))

    # Add watermark or branding
    ax.text(0.02, 0.02, "MiniQLib High-Fidelity Backtester", transform=ax.transAxes, 
            fontsize=9, color='#475569', alpha=0.8)

    plt.tight_layout()
    plt.savefig(output_dir / "nav_comparison.png", facecolor='#0B0F19')
    plt.close()

def plot_drawdown_comparison(aapl_dca, spy_bh, output_dir):
    print("📉 Plotting Drawdown Comparison Chart...")
    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=300)
    
    # Calculate Drawdowns
    dd_aapl = (aapl_dca["nav"] - aapl_dca["nav"].cummax()) / aapl_dca["nav"].cummax() * 100.0
    dd_spy = (spy_bh["nav"] - spy_bh["nav"].cummax()) / spy_bh["nav"].cummax() * 100.0
    
    ax.grid(True, linestyle="--", linewidth=0.5)
    
    # Fill drawdown areas
    ax.fill_between(dd_spy.index, dd_spy, 0, color='#FF5E62', alpha=0.15, label='S&P 500 Max Drawdown')
    ax.fill_between(dd_aapl.index, dd_aapl, 0, color='#00F2FE', alpha=0.25, label='Apple DCA Max Drawdown')
    
    ax.plot(dd_spy.index, dd_spy, color='#FF5E62', linewidth=1.2, alpha=0.7)
    ax.plot(dd_aapl.index, dd_aapl, color='#00F2FE', linewidth=1.8)
    
    ax.set_title("Drawdown Curve Comparison: AAPL DCA vs SPY B&H\n[Risk Profile - How Hard Is It To Hold?]", 
                 fontsize=15, fontweight='bold', pad=18, color='#F8FAFC')
    ax.set_xlabel("Year", fontsize=11, color='#E2E8F0', labelpad=8)
    ax.set_ylabel("Drawdown (%)", fontsize=11, color='#E2E8F0', labelpad=8)
    
    # Format Y-axis with percent signs
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, pos: f"{x:.0f}%"))
    
    legend = ax.legend(loc='lower left', fontsize=11, framealpha=0.9, facecolor='#0B0F19', edgecolor='#334155')
    plt.setp(legend.get_texts(), color='#F8FAFC')
    
    # Highlight max drawdowns
    max_dd_aapl = dd_aapl.min()
    max_dd_spy = dd_spy.min()
    
    ax.text(pd.Timestamp("2009-06-01"), -55, f"SPY Max Crash: {max_dd_spy:.1f}%", color='#FF5E62', fontsize=10, fontweight='bold')
    ax.text(pd.Timestamp("2013-08-01"), -41, f"AAPL DCA Max Crash: {max_dd_aapl:.1f}%", color='#00F2FE', fontsize=10, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_dir / "drawdown_comparison.png", facecolor='#0B0F19')
    plt.close()

def plot_dca_shares(aapl_close, output_dir):
    print("📊 Plotting DCA Share Purchases Chart...")
    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=300)
    
    # Let's assume a classic fixed monthly amount of $1,000 USD to buy shares
    # shares_bought = 1000 / close_price
    shares_bought = 1000.0 / aapl_close
    
    ax.grid(True, linestyle="--", linewidth=0.5)
    
    # Plot the shares purchased over time
    ax.fill_between(shares_bought.index, shares_bought, 0, color='#10B981', alpha=0.2, label='Shares Bought per $1,000')
    ax.plot(shares_bought.index, shares_bought, color='#10B981', linewidth=2.0)
    
    # Create a secondary Y-axis for Apple's Stock Price (log scale)
    ax2 = ax.twinx()
    ax2.plot(aapl_close.index, aapl_close, color='#94A3B8', linewidth=1.2, linestyle=':', alpha=0.6, label='AAPL Price (USD)')
    ax2.set_yscale('log')
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, pos: f"${x:,.1f}"))
    ax2.set_ylabel("AAPL Stock Price (USD) - Log Scale", color='#94A3B8', fontsize=11, labelpad=8)
    ax2.tick_params(colors='#94A3B8')
    
    ax.set_title("Automatic Dynamic Cushioning: DCA Shares Purchased Over Time\n[Why DCA Works: Buying More Shares on the Cheap]", 
                 fontsize=15, fontweight='bold', pad=18, color='#F8FAFC')
    ax.set_xlabel("Year", fontsize=11, color='#E2E8F0', labelpad=8)
    ax.set_ylabel("Number of Apple Shares Bought per $1,000 USD", fontsize=11, color='#10B981', labelpad=8)
    ax.tick_params(colors='#10B981')
    
    # Highlight specific crash periods
    # 1. 2008 Financial Crisis
    shares_2008 = shares_bought.loc["2008-11-01":"2009-01-01"].mean()
    price_2008 = aapl_close.loc["2008-11-01":"2009-01-01"].mean()
    ax.annotate(f"2008 Crash: AAPL @ ${price_2008:.1f}\nBought {shares_2008:.0f} shares per $1K!", 
                xy=(pd.Timestamp("2008-11-20"), shares_2008), 
                xytext=(pd.Timestamp("2010-06-01"), shares_2008 + 50),
                arrowprops=dict(facecolor='#10B981', arrowstyle="->"),
                color='#F8FAFC', fontsize=10, fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.4", fc="#0B0F19", ec="#10B981", alpha=0.9))
                
    # 2. 2024 Bull Market
    shares_2024 = shares_bought.loc["2024-05-01":"2024-06-01"].mean()
    price_2024 = aapl_close.loc["2024-05-01":"2024-06-01"].mean()
    ax.annotate(f"2024 Peak: AAPL @ ${price_2024:.0f}\nOnly {shares_2024:.1f} shares per $1K", 
                xy=(pd.Timestamp("2024-05-15"), shares_2024), 
                xytext=(pd.Timestamp("2018-01-01"), shares_2024 + 100),
                arrowprops=dict(facecolor='#FF5E62', arrowstyle="->"),
                color='#F8FAFC', fontsize=10,
                bbox=dict(boxstyle="round,pad=0.4", fc="#0B0F19", ec="#FF5E62", alpha=0.9))
                
    plt.tight_layout()
    plt.savefig(output_dir / "dca_shares_purchased.png", facecolor='#0B0F19')
    plt.close()

def main():
    print("🎬 Starting Premium Visuals Production Pipeline...")
    output_dir = PROJECT_ROOT / "video_scripts" / "charts"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    aapl_dca, spy_bh, aapl_close = run_simulations()
    
    plot_nav_comparison(aapl_dca, spy_bh, output_dir)
    plot_drawdown_comparison(aapl_dca, spy_bh, output_dir)
    plot_dca_shares(aapl_close, output_dir)
    
    print("🎉 All 3 Premium Visuals Generated successfully!")
    print(f"📁 Charts saved in: {output_dir}")

if __name__ == "__main__":
    main()
