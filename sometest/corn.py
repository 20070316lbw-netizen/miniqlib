# corn.py — CornBucket 3D Label Encoder
#
# ┌─────────────────────────────────────────────────────────────────┐
# │                     CORNBUCKET ARCHITECTURE                     │
# │                                                                 │
# │   r (截面收益分位数)        g (情绪因子)                          │
# │         │                       │                               │
# │         └──────────┬────────────┘                               │
# │                    ▼                                            │
# │           Bucket Assignment                                     │
# │           k = ⌊r · K⌋,  K=5                                      │
# │                    │                                            │
# │                    ▼                                            │
# │           Intra-bucket Score                                    │
# │           s = r - k/K                                           │
# │                    │                                            │
# │                    ▼                                            │
# │           Label Encode  ◄── 核心                                │
# │           label = k + α·s + β·g                                 │
# │           α=0.5  β=0.3  (固定，不可学习)                         │
# │                    │                                            │
# │                    ▼                                            │
# │           LightGBM LambdaRank                                   │
# │           objective=lambdarank, group=截面日期                   │
# │                    │                                            │
# │                    ▼                                            │
# │           截面排序 → Rank IC / IR / Sharpe                       │
# └─────────────────────────────────────────────────────────────────┘
#
# 对比实验:
#   baseline : CSRankNorm 回归          (当前基线)
#   exp_A    : encoded label + β=0.3   (验证3D结构+情绪)
#   exp_B    : encoded label + β=0.0   (剥离情绪贡献)

import numpy as np
import pandas as pd
import lightgbm as lgb
from typing import Optional


# ─────────────────────────────────────────────
# 超参数（固定，不可学习）
# ─────────────────────────────────────────────

K     = 5    # 桶子塔层数
ALPHA = 0.5  # 桶内分数权重
BETA  = 0.3  # 情绪门控权重


# ─────────────────────────────────────────────
# 第一层：Bucket Assignment
# k = ⌊r · K⌋,  r ∈ [0,1]
# ─────────────────────────────────────────────

def assign_bucket(r: np.ndarray, K: int = K) -> np.ndarray:
    """
    将截面收益分位数 r 映射到桶层编号 k。
    Map cross-sectional return quantile r to bucket layer index k.

    Args:
        r: 截面收益归一化分位数，shape (N,)，值域 [0, 1]
           Cross-sectional normalized return quantile, shape (N,), range [0, 1]
        K: 桶子塔层数，默认 5
           Number of bucket layers, default 5

    Returns:
        k: 桶层编号，shape (N,)，值域 {0, 1, ..., K-1}
           Bucket layer index, shape (N,), range {0, 1, ..., K-1}
    """
    # k = clip(floor(r * K), 0, K-1)
    k = np.floor(r * K).astype(int)
    return np.clip(k, 0, K - 1)


# ─────────────────────────────────────────────
# 第二层：Intra-bucket Score
# s = r - k/K,  s ∈ [0, 1/K)
# ─────────────────────────────────────────────

def intra_bucket_score(r: np.ndarray, k: np.ndarray, K: int = K) -> np.ndarray:
    """
    计算桶内相对分数 s，表示股票在桶内的细粒度位置。
    Calculate intra-bucket score s, representing the fine-grained position within the bucket.

    Args:
        r: 截面收益分位数，shape (N,)
           Cross-sectional return quantile, shape (N,)
        k: 桶层编号，shape (N,)
           Bucket layer index, shape (N,)
        K: 桶子塔层数
           Number of bucket layers

    Returns:
        s: 桶内分数，shape (N,)，值域 [0, 1/K)
           Intra-bucket score, shape (N,), range [0, 1/K)
    """
    # s = r - k / K
    return r - k / K


# ─────────────────────────────────────────────
# 第三层：Sentiment Gate
# g = clip(sentiment_norm, -1, 1)
# ─────────────────────────────────────────────

def sentiment_gate(
    sentiment_norm: Optional[np.ndarray],
    beta: float = BETA
) -> np.ndarray:
    """
    情绪门控修正项。
    beta=0.0 时退化为 exp_B（无情绪），用于消融实验。
    Sentiment gate modification term.
    Degenerates to exp_B (no sentiment) when beta=0.0, used for ablation experiments.

    Args:
        sentiment_norm: 归一化情绪因子，shape (N,)；为 None 时自动置零
                        Normalized sentiment factor, shape (N,); defaults to zero if None
        beta          : 情绪权重，0.0 表示关闭情绪通道
                        Sentiment weight, 0.0 means closing the sentiment channel

    Returns:
        g: 门控值，shape (N,)，值域 [-beta, beta]
           Gated value, shape (N,), range [-beta, beta]
    """
    if sentiment_norm is None or beta == 0.0:
        if sentiment_norm is not None:
            return np.zeros_like(sentiment_norm)
        return 0.0
    return np.clip(sentiment_norm, -1, 1) * beta


# ─────────────────────────────────────────────
# 核心：Label Encode
# label = k + α·s + β·g
# ─────────────────────────────────────────────

def encode_label(
    r: np.ndarray,
    sentiment_norm: Optional[np.ndarray] = None,
    K: int     = K,
    alpha: float = ALPHA,
    beta: float  = BETA,
) -> np.ndarray:
    """
    将 (r, sentiment_norm) 编码为 LightGBM lambdarank 可直接使用的 label。
    Encode (r, sentiment_norm) into a label that LightGBM lambdarank can directly use.

    权重关系保证层级主导，不发生跨层混淆：
    Hierarchy-dominant weighting ensures no cross-layer confusion:
        层间间距 = 1
        alpha·s  < 0.2   (s < 1/K = 0.2)
        beta·g   ∈ [-0.3, 0.3]

    Args:
        r             : 截面收益分位数，shape (N,)
                        Cross-sectional return quantile, shape (N,)
        sentiment_norm: 归一化情绪因子，shape (N,)；None 时忽略
                        Normalized sentiment factor, shape (N,); ignored if None
        K             : 桶层数
                        Number of bucket layers
        alpha         : 桶内分数权重
                        Intra-bucket score weight
        beta          : 情绪门控权重（消融时传 0.0）
                        Sentiment gate weight (0.0 for ablation)

    Returns:
        label: 编码后标签，shape (N,)，非负连续值
               Encoded label, shape (N,), non-negative continuous values
    """
    # 1. Bucket Assignment
    k = assign_bucket(r, K)
    # 2. Intra-bucket Score
    s = intra_bucket_score(r, k, K)
    # 3. Sentiment Gate
    g = sentiment_gate(sentiment_norm, beta)
    # 4. Label fusion
    return k + alpha * s + g


# ─────────────────────────────────────────────
# 数据接口：build_dataset
# 对接 miniqlib 的 build_dataset 约定
# ─────────────────────────────────────────────

def build_dataset(
    X: pd.DataFrame,
    r: pd.Series,
    sentiment_norm: Optional[pd.Series] = None,
    beta: float = BETA,
    is_train: bool = True,
) -> lgb.Dataset:
    """
    构造 LightGBM Dataset，group 按截面日期划分。
    Construct LightGBM Dataset, with group divided by cross-sectional date.

    仅训练集做 label 编码；测试集 label 置 None（与 Qlib 约定一致）。
    Only training set gets label encoding; test set label is set to None (consistent with Qlib).

    Args:
        X             : 特征矩阵，index 为 (date, stock) MultiIndex
                        Feature matrix, with index as (date, stock) MultiIndex
        r             : 截面收益分位数，同 index
                        Cross-sectional return quantile, same index
        sentiment_norm: 情绪因子，同 index；None 时忽略
                        Sentiment factor, same index; ignored if None
        beta          : 情绪权重
                        Sentiment weight
        is_train      : True=训练集编码label，False=测试集label置None
                        True=encode label for training, False=set test label to None

    Returns:
        lgb.Dataset
    """
    # 确保 X, r, sentiment_norm 索引严格对齐并排好序，以使截面组物理连续
    # Ensure indices are strictly aligned and sorted to keep cross-sectional groups contiguous
    X = X.sort_index()
    r = r.reindex(X.index)
    if sentiment_norm is not None:
        sentiment_norm = sentiment_norm.reindex(X.index)

    # 统计每个日期的样本数作为 LightGBM 的 Group 长度
    # Count the number of samples per date to define Group sizes for LightGBM
    group_sizes = X.groupby(level='date').size().values

    if is_train:
        # 编码标签 / Encode the labels
        r_val = r.values
        sent_val = sentiment_norm.values if sentiment_norm is not None else None
        label = encode_label(r_val, sent_val, K=K, alpha=ALPHA, beta=beta)
        
        # 将连续标签映射为 [0, 30] 之间的整数以适配 LightGBM LambdaRank 算法要求
        # Map continuous labels to [0, 30] integers to suit LightGBM LambdaRank requirements
        l_min, l_max = label.min(), label.max()
        if l_max > l_min:
            label = np.floor((label - l_min) * (30.0 / (l_max - l_min + 1e-8))).astype(int)
        else:
            label = np.zeros_like(label, dtype=int)
    else:
        label = None

    return lgb.Dataset(X, label=label, group=group_sizes, free_raw_data=False)


# ---------------------------------------------
# 评估：rank_ic_series
# ---------------------------------------------

def rank_ic_series(
    pred: pd.Series,
    r: pd.Series,
) -> pd.Series:
    """
    按日期计算截面 Rank IC 序列。
    Calculate the cross-sectional Rank IC series by date.

    Args:
        pred: 模型预测分数，index 为 (date, stock) MultiIndex
              Model predicted score, with index as (date, stock) MultiIndex
        r   : 真实收益分位数，同 index
              True return quantile, same index

    Returns:
        ic_series: 每日 Rank IC，index 为 date
                   Daily Rank IC, with index as date
    """
    # 结合在一个 DataFrame 中以确保在每日 groupby 时两列完美对齐
    # Combine into a DataFrame to ensure the two columns align perfectly when grouping daily
    df = pd.DataFrame({"pred": pred, "r": r})
    
    # 每日计算预测值与真实收益分位数之间的 Spearman 秩相关系数
    # Calculate Spearman rank correlation daily between predicted score and true return quantile
    def calc_spearman(group):
        # 如果样本太少，返回 NaN
        # If there are too few samples, return NaN
        if len(group) < 2:
            return np.nan
        return group["pred"].corr(group["r"], method="spearman")

    return df.groupby(level="date").apply(calc_spearman)


def evaluate(pred: pd.Series, r: pd.Series) -> dict:
    """
    输出完整评估指标。
    Output complete evaluation metrics.

    Returns:
        {
            "rank_ic_mean": float,
            "rank_ic_std" : float,
            "ir"          : float,   # IC / std
            "sharpe"      : float,   # 简单多空组合
        }
    """
    # 1. 计算 Rank IC 序列并统计其均值、标准差与 ICIR
    # 1. Calculate Rank IC series, its mean, standard deviation, and ICIR
    ic_series = rank_ic_series(pred, r)
    ic_mean = float(ic_series.mean())
    ic_std = float(ic_series.std())
    ir = ic_mean / ic_std if ic_std > 1e-12 else 0.0

    # 2. 构造每日等权多空组合并计算年化 Sharpe
    # 2. Construct daily equal-weighted long-short portfolio and calculate annualized Sharpe
    df = pd.DataFrame({"pred": pred, "r": r})

    def calc_ls_return(group):
        n = len(group)
        if n < 2:
            return 0.0
        # 做多预测值最高的前 20% 股票，做空最低的 20% 股票
        # Long the top 20% and short the bottom 20% of predicted scores
        k = max(1, int(n * 0.2))
        sorted_group = group.sort_values("pred")
        long_return = sorted_group["r"].iloc[-k:].mean()
        short_return = sorted_group["r"].iloc[:k].mean()
        return long_return - short_return

    ls_returns = df.groupby(level="date").apply(calc_ls_return)
    ls_mean = ls_returns.mean()
    ls_std = ls_returns.std()
    
    # 简单年化 Sharpe 比率 (假设一年 252 个交易日)
    # Simple annualized Sharpe ratio (assuming 252 trading days per year)
    if ls_std > 1e-12:
        sharpe = float((ls_mean / ls_std) * np.sqrt(252))
    else:
        sharpe = 0.0

    return {
        "rank_ic_mean": ic_mean,
        "rank_ic_std": ic_std,
        "ir": ir,
        "sharpe": sharpe,
    }


# ---------------------------------------------
# 实验入口
# ---------------------------------------------

def run_experiment(
    X_train, r_train, X_test, r_test,
    sentiment_train=None, sentiment_test=None,
    experiment: str = "exp_A",   # "baseline" | "exp_A" | "exp_B"
):
    """
    一键跑单组实验。
    Run a single experiment.

    experiment:
        baseline - CSRankNorm 回归，beta 无效
                   CSRankNorm regression, beta is invalid
        exp_A    - CornBucket + 情绪，beta=0.3
                   CornBucket + sentiment, beta=0.3
        exp_B    - CornBucket 无情绪，beta=0.0
                   CornBucket no sentiment, beta=0.0
    """
    from mini_qlib.utils.config import load_config
    from pathlib import Path

    # 1. 加载关于模型的参数配置文件
    # 1. Load config file about model parameters
    config_path = Path(__file__).resolve().parent.parent / "test_yaml" / "about_corn.yaml"
    cfg = load_config(config_path)

    # 2. 根据实验方案确定 beta 权重与目标函数类型
    # 2. Determine beta weight and objective based on the experiment
    if experiment == "baseline":
        beta = 0.0
        objective = "regression"
        metric = "rmse"
    elif experiment == "exp_A":
        beta = BETA  # 默认 0.3
        objective = "lambdarank"
        metric = "ndcg"
    elif experiment == "exp_B":
        beta = 0.0
        objective = "lambdarank"
        metric = "ndcg"
    else:
        raise ValueError(f"Unknown experiment: {experiment}")

    # 3. 从配置中读取 LightGBM 参数与训练控制参数
    # 3. Read LightGBM parameters and training control from config
    lgb_params = cfg.get("model", {}).copy()
    lgb_params["objective"] = objective
    lgb_params["metric"] = metric
    
    # 4. 执行按时间先后的时序验证集切分 (Chronological Split)
    # 4. Perform chronological split for validation set
    valid_frac = cfg.get("train_control", {}).get("valid_frac", 0.2)
    dates = X_train.index.get_level_values("date").unique().sort_values()
    
    if len(dates) > 2 and valid_frac > 0:
        split_idx = int(len(dates) * (1 - valid_frac))
        train_dates = dates[:split_idx]
        valid_dates = dates[split_idx:]
        
        X_tr = X_train.loc[train_dates]
        r_tr = r_train.loc[train_dates]
        sent_tr = sentiment_train.loc[train_dates] if sentiment_train is not None else None
        
        X_val = X_train.loc[valid_dates]
        r_val = r_train.loc[valid_dates]
        sent_val = sentiment_train.loc[valid_dates] if sentiment_train is not None else None
    else:
        # 兜底：如果不满足划分条件，则全量作为训练与验证
        # Fallback: if split conditions are not met, use full dataset
        X_tr, r_tr, sent_tr = X_train, r_train, sentiment_train
        X_val, r_val, sent_val = X_train, r_train, sentiment_train

    # 5. 构造 LightGBM 训练集与验证集
    # 5. Construct LightGBM training and validation datasets
    if objective == "lambdarank":
        train_set = build_dataset(X_tr, r_tr, sent_tr, beta=beta, is_train=True)
        valid_set = build_dataset(X_val, r_val, sent_val, beta=beta, is_train=True)
    else:
        # baseline 回归方案 / baseline regression setup
        # 对回归方案对齐排序，使其能直接利用 numpy.values
        X_tr = X_tr.sort_index()
        r_tr = r_tr.reindex(X_tr.index)
        X_val = X_val.sort_index()
        r_val = r_val.reindex(X_val.index)
        
        train_set = lgb.Dataset(X_tr, label=r_tr.values)
        valid_set = lgb.Dataset(X_val, label=r_val.values)

    # 6. 配置早停回调与训练轮数
    # 6. Configure early stopping callbacks and training rounds
    callbacks = []
    early_stopping_rounds = cfg.get("train_control", {}).get("early_stopping", 50)
    if early_stopping_rounds > 0:
        callbacks.append(lgb.early_stopping(early_stopping_rounds))

    num_boost_round = cfg.get("train_control", {}).get("num_boost_round", 1000)

    # 7. 启动 LightGBM 训练
    # 7. Start LightGBM training
    model = lgb.train(
        lgb_params,
        train_set,
        num_boost_round=num_boost_round,
        valid_sets=[valid_set],
        callbacks=callbacks
    )

    # 8. 对测试集进行预测并计算评估指标
    # 8. Predict on test set and calculate evaluation metrics
    pred = model.predict(X_test)
    pred_series = pd.Series(pred, index=X_test.index)

    return evaluate(pred_series, r_test)


def generate_mock_prices(start_date="2016-05-18", end_date="2026-05-15", num_tickers=20):
    """
    生成高保真的模拟股票日线行情数据。
    Generate high-fidelity simulated daily stock price data.
    """
    tickers = [f"STK{i:02d}" for i in range(num_tickers)]
    dates = pd.date_range(start=start_date, end=end_date, freq="B") # 仅工作日 / business days
    
    records = []
    np.random.seed(42)
    
    for ticker in tickers:
        # 初始股价与随机漫步参数 / Initial price and random walk parameters
        price = np.random.uniform(10.0, 100.0)
        volatility = np.random.uniform(0.01, 0.03) # 日波动率
        
        for dt in dates:
            # 几何布朗运动随机漫步 / Geometric Brownian Motion random walk
            pct_change = np.random.normal(0.0002, volatility) # 微弱正向漂移
            close_price = price * (1 + pct_change)
            open_price = price * (1 + np.random.normal(0, volatility * 0.3))
            high_price = max(close_price, open_price) * (1 + abs(np.random.normal(0, volatility * 0.2)))
            low_price = min(close_price, open_price) * (1 - abs(np.random.normal(0, volatility * 0.2)))
            volume = int(np.random.lognormal(14, 1))
            
            records.append({
                "date": dt,
                "ticker": ticker,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume
            })
            price = close_price # 滚到下一期
            
    df = pd.DataFrame(records)
    # 确保字段类型一致 / Ensure consistent field types
    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = df["ticker"].astype(str)
    return df


if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    # 确保 Windows 下能够正确打印 UTF-8 编码的文字
    # Ensure Windows console correctly prints UTF-8 encoded text
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
        
    # 添加项目根目录和 sometest 目录到 python 路径
    # Add project root and sometest to python path
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT / "sometest"))

    print("======================================================================")
    print("Beginning CornBucket 3D Rank Model End-to-End Smoke Test")
    print("======================================================================")

    # 1. 尝试从数据库读取价格数据
    # 1. Try to read price data from the database
    from mini_qlib.data.load_data import read_prices, get_db, init_prices_table, insert_prices
    
    print("Connecting to database and checking price data...")
    db_ok = False
    try:
        df_prices = read_prices()
        if df_prices.empty:
            print("Database is empty, generating high-fidelity simulated prices and writing to DB...")
            df_mock = generate_mock_prices()
            with get_db() as con:
                init_prices_table(con)
                insert_prices(con, df_mock)
            print("Mock prices successfully written to database!")
            df_prices = read_prices()
        print(f"Database loaded successfully, containing {len(df_prices)} rows.")
        db_ok = True
    except Exception as e:
        print(f"Database read/write failed (might be locked or permissions issue): {e}")
        print("Automatically falling back to in-memory simulated data source!")
        df_prices = generate_mock_prices()

    # 2. 计算特征和标签
    # 2. Calculate features and labels
    print("\nGenerating quantitative features and excess return labels...")
    from old_feature_label.make_features import make_features, FEATURE_COLS
    from old_feature_label.make_labels import make_label

    # 计算特征 / Calculate features
    df_prices = make_features(df_prices)
    # 计算标签 / Calculate labels
    label_5d = make_label(df_prices, n_periods=5)
    
    # 挂回 DataFrame / Attach back to DataFrame
    df_prices["label_5d"] = label_5d
    
    # 清理含 NaN 的数据行 (如每只股票最开始或最后几行)
    # Clean rows with NaN in features or label
    df_prices = df_prices.dropna(subset=FEATURE_COLS + ["label_5d"])
    
    # 构造横截面收益分位数 r (值域在 [0, 1] 之间)
    # Construct cross-sectional return quantile r (range between [0, 1])
    df_prices["r"] = df_prices.groupby("date")["label_5d"].rank(pct=True)
    
    # 构造情绪因子 (均值为 0，标准差为 1)
    # Construct sentiment factor (mean=0, std=1)
    np.random.seed(42)
    df_prices["sentiment_norm"] = np.random.normal(0, 1, len(df_prices))
    
    # 将 index 设置为 MultiIndex (date, ticker)
    # Set index to MultiIndex (date, ticker)
    df_prices = df_prices.set_index(["date", "ticker"]).sort_index()
    
    # 提取特征、收益分位数 and 情绪
    # Extract features, return quantile, and sentiment
    X = df_prices[FEATURE_COLS]
    r = df_prices["r"]
    sentiment = df_prices["sentiment_norm"]

    # 3. 按配置文件切分训练集与测试集
    # 3. Split train and test set according to config
    from mini_qlib.utils.config import load_config
    cfg = load_config(PROJECT_ROOT / "test_yaml" / "about_corn.yaml")
    
    train_start = pd.to_datetime(cfg["data"]["splits"]["train"]["start"])
    train_end = pd.to_datetime(cfg["data"]["splits"]["train"]["end"])
    test_start = pd.to_datetime(cfg["data"]["splits"]["test"]["start"])
    test_end = pd.to_datetime(cfg["data"]["splits"]["test"]["end"])
    
    # 获取索引中的日期 / Get index dates
    idx_dates = X.index.get_level_values("date")
    
    # 划分数据集 / Split datasets
    train_mask = (idx_dates >= train_start) & (idx_dates <= train_end)
    test_mask = (idx_dates >= test_start) & (idx_dates <= test_end)
    
    X_train, r_train, sentiment_train = X[train_mask], r[train_mask], sentiment[train_mask]
    X_test, r_test, sentiment_test = X[test_mask], r[test_mask], sentiment[test_mask]
    
    print(f"Dataset split complete:")
    print(f"  - Training range: {train_start.strftime('%Y-%m-%d')} to {train_end.strftime('%Y-%m-%d')} ({len(X_train)} rows)")
    print(f"  - Testing range: {test_start.strftime('%Y-%m-%d')} to {test_end.strftime('%Y-%m-%d')} ({len(X_test)} rows)")

    # 4. 顺次运行三组对比实验
    # 4. Run the three comparative experiments sequentially
    results = {}
    for exp_name in ["baseline", "exp_A", "exp_B"]:
        print(f"\n------------------------------------------------------")
        print(f"Training and evaluating experiment: {exp_name} ...")
        print(f"------------------------------------------------------")
        metrics = run_experiment(
            X_train, r_train, X_test, r_test,
            sentiment_train, sentiment_test,
            experiment=exp_name
        )
        results[exp_name] = metrics
        print(f"Finished evaluation for {exp_name}:")
        print(f"   Rank IC Mean: {metrics['rank_ic_mean']:.4f}")
        print(f"   Rank IC Std: {metrics['rank_ic_std']:.4f}")
        print(f"   ICIR: {metrics['ir']:.4f}")
        print(f"   Long-Short Sharpe: {metrics['sharpe']:.4f}")

    # 5. 美丽格式输出对比结果表格
    # 5. Print beautiful comparative summary table
    print("\n" + "="*80)
    print(f"{'Experiment Comparison Summary':^80}")
    print("="*80)
    print(f"{'Experiment':<20} | {'Rank IC Mean':^12} | {'Rank IC Std':^12} | {'ICIR':^10} | {'L-S Sharpe':^12}")
    print("-"*80)
    for name, m in results.items():
        print(f"{name:<20} | {m['rank_ic_mean']:^12.4f} | {m['rank_ic_std']:^12.4f} | {m['ir']:^10.4f} | {m['sharpe']:^12.4f}")
    print("="*80)