"""
================================================================================
                    MiniQLib Config-driven Quant Pipeline
================================================================================

本文件实现了可插拔的配置链量化计算与训练流水线 (run_pipeline.py)。
整个流水线完全由 `config_pipeline.yaml` 驱动，执行如下五个标准工业级步骤：
1. 数据加载与格式规范化：从 DuckDB 读取标普500历史行情，转为规范的多股票 MultiIndex (date, ticker) DataFrame。
2. 因子编译与计算：实例化 DataHandler，动态解析并编译注册制或自定义因子与标签公式，结合共享 context 缓存极速算图。
3. 高防保真数据集切分 (Embargo)：判定隔离带开关，在时序分割时自动顺延交易日，防止未来价格数据发生任何 Look-Ahead 泄漏。
4. 机器学习模型训练：训练 LightGBM 回归模型，自动使用验证集进行 Early Stopping 调优。
5. 多维截面业绩评估：对测试集预测值进行横截面 Rank IC、IR (信息比率)、t 统计量及胜率的系统级评估，并打印报表。
"""
import os
import sys
import yaml
import numpy as np
import pandas as pd
import lightgbm as lgb
from pathlib import Path

# Ensure Windows console prints emoji and UTF-8 characters safely
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# ──────────────────────────────────────────────────────────────────────────
# 1. 规避 ModuleNotFoundError 坑，确保根目录在 sys.path 中
# ──────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "mini_qlib"))

from mini_qlib.data.load_data import read_prices
from mini_qlib.data.handler import DataHandler


def load_config(config_path: Path) -> dict:
    """读取并解析 YAML 配置文件"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def calculate_embargo_dates(
    dates: pd.DatetimeIndex, 
    train_end: pd.Timestamp, 
    valid_end: pd.Timestamp, 
    embargo_days: int
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """
    基于真实的交易日历列表，自动向后推延交易日天数作为隔离带，计算安全的 valid_start 与 test_start。
    """
    sorted_days = sorted(dates.unique())
    
    # 计算安全的 valid_start
    if train_end in sorted_days:
        idx_train = sorted_days.index(train_end)
        idx_valid_start = min(idx_train + embargo_days, len(sorted_days) - 1)
        valid_start = sorted_days[idx_valid_start]
    else:
        # 如果 train_end 不在交易日中，找最近的后一天
        valid_start = train_end + pd.Timedelta(days=1)
        
    # 计算安全的 test_start
    if valid_end in sorted_days:
        idx_valid = sorted_days.index(valid_end)
        idx_test_start = min(idx_valid + embargo_days, len(sorted_days) - 1)
        test_start = sorted_days[idx_test_start]
    else:
        test_start = valid_end + pd.Timedelta(days=1)
        
    return valid_start, test_start


def evaluate_rank_ic(pred: pd.Series, label: pd.Series) -> pd.DataFrame:
    """
    计算横截面每日 Spearman Rank IC，并总结均值、标准差、IR、t 统计量与胜率。
    """
    eval_df = pd.concat([pred.rename("pred"), label.rename("label")], axis=1).dropna()
    
    # 逐日计算 Spearman 秩相关系数
    daily_ic_series = eval_df.groupby(level="date", group_keys=False).apply(
        lambda g: g["pred"].rank().corr(g["label"].rank())
    ).dropna()
    
    ic_mean = daily_ic_series.mean()
    ic_std = daily_ic_series.std()
    ic_count = len(daily_ic_series)
    
    ir = ic_mean / ic_std if ic_std > 0 else np.nan
    t_stat = ic_mean / (ic_std / np.sqrt(ic_count)) if ic_std > 0 and ic_count > 0 else np.nan
    win_ratio = (daily_ic_series > 0).mean() if ic_count > 0 else np.nan
    
    return pd.DataFrame({
        "指标 (Metrics)": ["Rank IC 均值", "Rank IC 标准差", "信息比率 (IR)", "t 统计量 (t-stat)", "正 IC 占比 (胜率)"],
        "数值 (Values)": [ic_mean, ic_std, ir, t_stat, win_ratio]
    })


def main():
    print("=" * 70)
    print("🚀 MiniQLib 配置链驱动流水线启动 / Config-driven Pipeline Started")
    print("=" * 70)
    
    # 1. 加载配置 (Load Pipeline Config)
    config_file = PROJECT_ROOT / "config_pipeline.yaml"
    if not config_file.exists():
        print(f"❌ 配置文件不存在: {config_file}")
        sys.exit(1)
        
    print(f"📂 加载流水线配置文件: {config_file}")
    config = load_config(config_file)
    
    # 2. 从数据库拉取行情并转换为规范的 MultiIndex (date, ticker) 格式
    print("💽 正在从数据库加载原始日频行情价格数据...")
    raw_df = read_prices()
    if raw_df.empty:
        print("❌ 数据库为空！请先运行 scripts 目录下的 fetch 脚本下载数据。")
        sys.exit(1)
        
    raw_df["date"] = pd.to_datetime(raw_df["date"])
    # 设定为规范的 MultiIndex
    df = raw_df.set_index(["date", "ticker"]).sort_index()
    print(f"   成功加载 {len(df)} 行原始量价行情")
    
    # 3. 实例化 DataHandler 并执行高保真因子/标签 AST 计算
    print("\n🏗️ 正在编译并计算因子与标签计算图 (DataHandler compilation)...")
    handler = DataHandler(df, config["data_handler"])
    processed_df = handler.setup()
    print(f"   因子与标签结算完毕，最终矩阵形状: {processed_df.shape}")
    
    # 4. 数据切分与时序隔离带处理
    print("\n⏳ 正在进行时序数据集划分 (Dataset segments splitting)...")
    seg_conf = config["data_loader"]["segments"]
    train_start = pd.Timestamp(seg_conf["train"]["start"])
    train_end = pd.Timestamp(seg_conf["train"]["end"])
    valid_end = pd.Timestamp(seg_conf["valid"]["end"])
    test_end = pd.Timestamp(seg_conf["test"]["end"])
    
    embargo_safety = config["data_loader"].get("embargo_safety", True)
    embargo_days = config["data_loader"].get("embargo_days", 0)
    
    # 提取所有交易日列表
    trading_dates = processed_df.index.get_level_values("date").unique().sort_values()
    
    if embargo_safety and embargo_days > 0:
        valid_start, test_start = calculate_embargo_dates(
            trading_dates, train_end, valid_end, embargo_days
        )
        print(f"   🛡️ 隔离带 (Embargo) 已启用：自动后延 {embargo_days} 个交易日")
        print(f"       [训练集] {train_start.strftime('%Y-%m-%d')} 至 {train_end.strftime('%Y-%m-%d')}")
        print(f"       [隔离带] 自动剥离，避开数据泄露")
        print(f"       [验证集] 顺延至 {valid_start.strftime('%Y-%m-%d')} 至 {valid_end.strftime('%Y-%m-%d')}")
        print(f"       [测试集] 顺延至 {test_start.strftime('%Y-%m-%d')} 至 {test_end.strftime('%Y-%m-%d')}")
    else:
        valid_start = pd.Timestamp(seg_conf["valid"]["start"])
        test_start = pd.Timestamp(seg_conf["test"]["start"])
        print("   ⚠️ 警告：未启用时序隔离带 (Embargo)，训练与验证交界处可能存在前瞻偏差泄露！")
        
    dt = processed_df.index.get_level_values("date")
    train_df = processed_df.loc[(dt >= train_start) & (dt <= train_end)].dropna()
    valid_df = processed_df.loc[(dt >= valid_start) & (dt <= valid_end)].dropna()
    test_df = processed_df.loc[(dt >= test_start) & (dt <= test_end)].dropna()
    
    print(f"   划分完成：训练集样本数={len(train_df)} | 验证集样本数={len(valid_df)} | 测试集样本数={len(test_df)}")
    if train_df.empty or test_df.empty:
        print("❌ 警告：切分后样本数为0，请确认数据库时间跨度是否涵盖您的配置区间。")
        sys.exit(1)
        
    # 5. 机器学习模型训练 (LightGBM Training)
    print("\n🌲 正在训练 LightGBM 机器学习模型...")
    feat_cols = [c for c in processed_df.columns if c != "label"]
    
    # 字典合并：保证默认超参存在的同时，支持 YAML 的个性化覆盖
    model_conf = config.get("model", {})
    lgb_params = {
        "objective": model_conf.get("objective", "regression"),
        "metric": model_conf.get("metric", "rmse"),
        "learning_rate": model_conf.get("learning_rate", 0.05),
        "num_leaves": model_conf.get("num_leaves", 31),
        "feature_fraction": model_conf.get("feature_fraction", 0.9),
        "bagging_fraction": model_conf.get("bagging_fraction", 0.8),
        "bagging_freq": model_conf.get("bagging_freq", 5),
        "min_data_in_leaf": model_conf.get("min_data_in_leaf", 20),
        "verbose": model_conf.get("verbose", -1),
    }
    num_boost_round = model_conf.get("num_boost_round", 150)
    early_stopping_rounds = model_conf.get("early_stopping_rounds", 25)
    
    dtrain = lgb.Dataset(train_df[feat_cols], label=train_df["label"])
    valid_sets = [dtrain]
    callbacks = [lgb.log_evaluation(period=50)]
    
    if not valid_df.empty:
        dvalid = lgb.Dataset(valid_df[feat_cols], label=valid_df["label"], reference=dtrain)
        valid_sets.append(dvalid)
        callbacks.append(lgb.early_stopping(early_stopping_rounds, verbose=False))
        
    model = lgb.train(
        lgb_params,
        dtrain,
        num_boost_round=num_boost_round,
        valid_sets=valid_sets,
        callbacks=callbacks
    )
    print("   ✅ LightGBM 模型训练圆满成功！")
    
    # 6. 多维横截面评估 (Rank IC & IR Evaluation)
    print("\n📊 正在对测试集 (Test Dataset) 执行多维横截面评估...")
    test_preds = model.predict(test_df[feat_cols])
    test_pred_series = pd.Series(test_preds, index=test_df.index)
    
    ic_report = evaluate_rank_ic(test_pred_series, test_df["label"])
    
    print("\n" + "=" * 55)
    print("📈 MiniQLib 因子预测流水线性能报告 (Performance Report)")
    print("=" * 55)
    print(ic_report.to_string(index=False, float_format=lambda x: f"{x: .6f}"))
    print("=" * 55)
    print("🎉 预测流水线全部流程执行完毕！")


if __name__ == "__main__":
    main()
