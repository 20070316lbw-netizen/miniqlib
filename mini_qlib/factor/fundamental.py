# -*- coding: utf-8 -*-
"""
================================================================================
                    MiniQLib Point-in-Time Fundamental Feature Library
================================================================================

This file implements and registers classic Point-in-Time (PIT) fundamental factor expressions.
These metrics leverage SEC EDGAR balance sheet, income, and cashflow data.
All factors are registered in the global feature_registry, allowing plug-and-play config-driven calculations.
本文件实现并注册经典的时点（Point-in-Time）财务基本面因子表达式。
这些指标利用了 SEC EDGAR 资产负债表、利润表和现金流量表数据。
所有因子均注册在全局 feature_registry 中，实现即插即用的配置链因子结算。
"""
from mini_qlib.data.expression import PFeature
from mini_qlib.factor.feature import feature_registry

# 1. 净资产收益率 (Return on Equity - ROE)
# Formula: Net Income / Stockholders' Equity
feature_registry.register(
    name="ROE",
    expr="$$net_income / $$equity",
    desc="净资产收益率 (ROE)：时点净利润除以时点股东权益"
)

# 2. 资产负债率 (Debt-to-Asset Ratio - Leverage)
# Formula: Total Liabilities / Total Assets
feature_registry.register(
    name="Leverage",
    expr="$$total_liabilities / $$total_assets",
    desc="资产负债率 (Leverage)：时点总负债除以时点总资产"
)

# 3. 营业利润率 (Operating profit margin - OpMargin)
# Formula: Operating Income / Revenue
feature_registry.register(
    name="OpMargin",
    expr="$$op_income / $$revenue",
    desc="营业利润率 (OpMargin)：时点营业利润除以时点营业收入"
)

# 4. 现金债务比 (Cash-to-Debt Ratio)
# Formula: Cash and Equivalents / Long-Term Debt
feature_registry.register(
    name="CashToDebt",
    expr="$$cash / ($$total_debt + 1e-12)",
    desc="现金债务比：时点货币资金除以长期负债总额"
)

# 5. 经营净现比 (CFO-to-NetIncome Ratio)
# Formula: Cash from Operations / Net Income
feature_registry.register(
    name="CFOToNetIncome",
    expr="$$cfo / ($$net_income + 1e-12)",
    desc="经营净现比：经营活动现金流净额除以时点净利润"
)
