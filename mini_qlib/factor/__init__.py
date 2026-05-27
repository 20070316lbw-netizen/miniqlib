# mini_qlib factor package / 因子打包与注册模块
# 本模块用于统一管理和实现高级复合因子（如 Alpha158 等）以及定制化财务比率因子。
# This module is used to manage and implement composite factors (like Alpha158) and customized financial ratios.

from .label import label_registry
from .feature import feature_registry

__all__ = ["label_registry", "feature_registry"]
