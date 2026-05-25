"""
用于测试的因子文件,包含一些常用因子
"""
import pandas as pd
import numpy as np

def _mom_1d(df: pd.DataFrame) -> pd.Series:
    return df.groupby('ticker')['close'].pct_change(1)

def _std_5d(df: pd.DataFrame) -> pd.Series:
    # 注意:它依赖 mom_1d 这一列已经存在 —— 这个依赖现在是【显式】的
    return (
        df.groupby('ticker')['mom_1d']
        .rolling(5).std()
        .reset_index(level=0, drop=True)
    )

# KMID  = (close - open) / open
# KLEN  = (high - low) / open
# KUP   = (high - max(open, close)) / open          # 上影线
# KLOW  = (min(open, close) - low) / open           # 下影线
# KSFT  = (2*close - high - low) / open             # 收盘在当日区间的相对位置
# KMID2 = (close - open) / (high - low + 1e-12)
def _kmid(df: pd.DataFrame) -> pd.Series:
    return (df['close'] - df['open']) / df['open']

def _klen(df: pd.DataFrame) -> pd.Series:
    return (df['high'] - df['low']) / df['open']

def _kup(df: pd.DataFrame) -> pd.Series:
    return (df["high"] - np.maximum(df["open"], df["close"])) / df["open"]

def _klow(df: pd.DataFrame) -> pd.Series:
    return (np.minimum(df["open"], df["close"]) - df["low"]) / df["open"]

def _ksft(df: pd.DataFrame) -> pd.Series:
    return (2 * df["close"] - df["high"] - df["low"]) / df["open"]

def _kmid_2(df: pd.DataFrame) -> pd.Series:
    return (df["close"] - df["open"]) / (df["high"] - df["low"] + 1e-12)


# ROC5  = close / close.shift(5)    # 今价/5天前价,涨了 >1(与 J&T1993 惯例一致)
# ROC20 = close / close.shift(20)
# ROC60 = close / close.shift(60)
# 必须 groupby('ticker'):否则 shift 会越过 ticker 边界取到上一只股票的价格
def _roc_5(df: pd.DataFrame) -> pd.Series:
    return df["close"] / df.groupby("ticker")["close"].shift(5)

def _roc_20(df: pd.DataFrame) -> pd.Series:
    return df["close"] / df.groupby("ticker")["close"].shift(20)

def _roc_60(df: pd.DataFrame) -> pd.Series:
    return df["close"] / df.groupby("ticker")["close"].shift(60)


# MA5  = close.rolling(5).mean()  / close
# MA20 = close.rolling(20).mean() / close
# MA60 = close.rolling(60).mean() / close
# 必须 groupby('ticker'):否则 rolling 窗口会跨股票边界混入上一只股票的尾部数据
def _ma_5(df: pd.DataFrame) -> pd.Series:
    ma = df.groupby("ticker")["close"].rolling(5).mean().reset_index(level=0, drop=True)
    return ma / df["close"]

def _ma_20(df: pd.DataFrame) -> pd.Series:
    ma = df.groupby("ticker")["close"].rolling(20).mean().reset_index(level=0, drop=True)
    return ma / df["close"]

def _ma_60(df: pd.DataFrame) -> pd.Series:
    ma = df.groupby("ticker")["close"].rolling(60).mean().reset_index(level=0, drop=True)
    return ma / df["close"]



# STD5  = close.rolling(5).std()  / close
# STD20 = close.rolling(20).std() / close
# STD60 = close.rolling(60).std() / close
# 必须 groupby('ticker'):同 MA,防 rolling 跨股票污染
def _std_5(df: pd.DataFrame) -> pd.Series:
    s = df.groupby("ticker")["close"].rolling(5).std().reset_index(level=0, drop=True)
    return s / df["close"]

def _std_20(df: pd.DataFrame) -> pd.Series:
    s = df.groupby("ticker")["close"].rolling(20).std().reset_index(level=0, drop=True)
    return s / df["close"]

def _std_60(df: pd.DataFrame) -> pd.Series:
    s = df.groupby("ticker")["close"].rolling(60).std().reset_index(level=0, drop=True)
    return s / df["close"]

def _rank_mom_5d(df: pd.DataFrame) -> pd.Series:
    # 自给自足:内部自算 5 日动量再做截面排名,不再依赖 mom_5d 列。
    # 这样 mom_5d 可以从 registry 彻底删掉(它与本因子高度共线)。
    mom5 = df.groupby("ticker")["close"].pct_change(5)
    return mom5.groupby(df["date"]).rank(pct=True)

# ---- 横截面因子:看个股在「当天全市场」里的相对位置 ----
# 设计原则:均基于「已验证干净」的时序因子做截面 rank,
# 不引入新的原始计算——控制变量,出错面最小。
# rank 默认 na_option='keep':源因子为 NaN 的行 rank 后仍是 NaN,
# 不会被错误地排进百分位。必须 groupby("date"):只在同一
# 交易日内比较,绝不跨日期。

def _rank_roc20(df: pd.DataFrame) -> pd.Series:
    # 中期动量的横截面强弱(Jegadeesh-Titman 动量异象)
    return df.groupby("date")["ROC20"].rank(pct=True)

def _rank_std20(df: pd.DataFrame) -> pd.Series:
    # 低波动异象——截面上波动率最低的那批股票
    return df.groupby("date")["STD20"].rank(pct=True)

def _rank_kmid(df: pd.DataFrame) -> pd.Series:
    # 当日实体涨跌的相对强弱(短期反转 / 日内强度)
    return df.groupby("date")["KMID"].rank(pct=True)

def _rank_ma20(df: pd.DataFrame) -> pd.Series:
    # 相对均线位置的截面排序(趋势 vs 回调)
    return df.groupby("date")["MA20"].rank(pct=True)

# ---- 登记表:这就是"做选择"的地方,谁先算谁后算一目了然 ----
# 顺序有意义:std_5d 在 mom_1d 之后,因为它依赖 mom_1d
FEATURE_REGISTRY = {
    "mom_1d": _mom_1d,
    "std_5d": _std_5d,
    "KMID": _kmid,
    "KMID2": _kmid_2,
    "KLEN": _klen,
    "KUP": _kup,
    "KLOW": _klow,
    "KSFT": _ksft,
    "ROC5": _roc_5,
    "ROC20": _roc_20,
    "ROC60": _roc_60,
    "MA5": _ma_5,
    "MA20": _ma_20,
    "MA60": _ma_60,
    "STD5": _std_5,
    "STD20": _std_20,
    "STD60": _std_60,
    "RANK_MOM_5D": _rank_mom_5d,
    # 横截面 rank 因子——必须注册在其依赖的源因子之后。
    # ROC20/STD20/KMID/MA20 均在上方已注册,make_features 按
    # 此顺序逐个计算,放末尾保证依赖列已存在。
    "RANK_ROC20": _rank_roc20,
    "RANK_STD20": _rank_std20,
    "RANK_KMID": _rank_kmid,
    "RANK_MA20": _rank_ma20,
}

# ===== single source of truth =====
# 特征名一律从这里取。train.py / evaluate.py 不准再自己手抄一份。
# 取的是 FEATURE_REGISTRY 实际注册的键——以「实际能算的」为准,
# 而不是以文档/记忆为准。以后加因子只需在 REGISTRY 里加一项,
# train 和 evaluate 自动同步,结构上不可能再出现错位。
FEATURE_COLS = list(FEATURE_REGISTRY.keys())

def make_features(df: pd.DataFrame) -> pd.DataFrame:
    """按登记表依次计算所有特征,挂回 df"""
    # reset_index(drop=True) 必须加:groupby-rolling 返回 MultiIndex,
    # 内层靠行号对齐回 df。不重置索引的话 sort_values 留下的
    # 乱序原索引会让 ma/df['close'] 的除法对齐出错。
    df = df.sort_values(['ticker', 'date']).reset_index(drop=True).copy()
    for name, fn in FEATURE_REGISTRY.items():
        df[name] = fn(df)
    return df
