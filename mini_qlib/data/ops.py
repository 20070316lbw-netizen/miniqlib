"""
本文件做 qlib 算子引擎的复刻版本
"""
import numpy as np
import pandas as pd

############# 复刻 qlib.data.ops.py ####################
class MiniExpression:
    """所有算子和特征的父类"""

    # 全局缓存字典
    _CACHE = {}

    def load(self):
        pass