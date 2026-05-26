#  Copyright (c) Microsoft Corporation.
#  Licensed under the MIT License.
"""
Qlib provides two kinds of interfaces.
(1) Users could define the Quant research workflow by a simple configuration.
(2) Qlib is designed in a modularized way and supports creating research workflow by code just like building blocks.

Qlib 提供了两种类型的接口：
(1) 用户可以通过简单的配置文件直接定义量化研究工作流。
(2) Qlib 采用模块化设计，支持像积木一样通过 Python 代码创建自定义的研究工作流。

The interface of (1) is `qrun XXX.yaml`.  The interface of (2) is script like this, which nearly does the same thing as `qrun XXX.yaml`

接口 (1) 的调用方式为 `qrun XXX.yaml`。接口 (2) 则是像下面这样的 Python 脚本，其执行的功能与 `qrun XXX.yaml` 几乎完全一致。
"""

import qlib
from qlib.constant import REG_CN
from qlib.utils import init_instance_by_config, flatten_dict
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord, SigAnaRecord
from qlib.tests.data import GetData
from qlib.tests.config import CSI300_BENCH, CSI300_GBDT_TASK

if __name__ == "__main__":
    # use default data
    # 使用默认的数据源与存储路径
    provider_uri = "~/.qlib/qlib_data/cn_data"  # target_dir  # 目标数据文件夹
    GetData().qlib_data(target_dir=provider_uri, region=REG_CN, exists_skip=True)
    qlib.init(provider_uri=provider_uri, region=REG_CN)

    # Initialize model and dataset by configuration dict
    # 根据配置字典动态初始化预测模型与数据集实例
    model = init_instance_by_config(CSI300_GBDT_TASK["model"])
    dataset = init_instance_by_config(CSI300_GBDT_TASK["dataset"])

    # Configure portfolio analysis, including executor, strategy, and backtest environment parameters
    # 配置投资组合回测分析参数，包括执行器、交易策略以及回测市场环境参数
    port_analysis_config = {
        "executor": {
            "class": "SimulatorExecutor",
            "module_path": "qlib.backtest.executor",
            "kwargs": {
                "time_per_step": "day",
                "generate_portfolio_metrics": True,
            },
        },
        "strategy": {
            "class": "TopkDropoutStrategy",
            "module_path": "qlib.contrib.strategy.signal_strategy",
            "kwargs": {
                "signal": (model, dataset),
                "topk": 50,
                "n_drop": 5,
            },
        },
        "backtest": {
            "start_time": "2017-01-01",
            "end_time": "2020-08-01",
            "account": 100000000,
            "benchmark": CSI300_BENCH,
            "exchange_kwargs": {
                "freq": "day",
                "limit_threshold": 0.095,
                "deal_price": "close",
                "open_cost": 0.0005,
                "close_cost": 0.0015,
                "min_cost": 5,
            },
        },
    }

    # NOTE: This line is optional
    # It demonstrates that the dataset can be used standalone.
    # 注意：这行代码是可选的
    # 它仅仅用于演示数据集（Dataset）是可以完全脱离模型独立被加载和准备的。
    example_df = dataset.prepare("train")
    print(example_df.head())

    # start experiment logging
    # 启动量化实验记录（基于底层的 MLflow 实验生命周期管理器）
    with R.start(experiment_name="workflow"):
        # Log all configuration parameters for perfect reproducibility
        # 记录所有配置参数以实现研究的可复现性
        R.log_params(**flatten_dict(CSI300_GBDT_TASK))
        
        # Fit the model using the prepared dataset
        # 使用准备好的数据集对预测模型进行拟合训练
        model.fit(dataset)
        
        # Save the trained model object to local pickle file
        # 将训练完毕的模型序列化并保存
        R.save_objects(**{"params.pkl": model})

        # prediction and record the model's out-of-sample predictions
        # 执行样本外预测并记录模型的预测信号
        recorder = R.get_recorder()
        sr = SignalRecord(model, dataset, recorder)
        sr.generate()

        # Signal Analysis (IC, IR, Rank IC, etc.)
        # 信号分析（统计并生成信息系数 IC、信息比率 IR、Rank IC 等评估指标）
        sar = SigAnaRecord(recorder)
        sar.generate()

        # backtest. If users want to use backtest based on their own prediction,
        # please refer to https://qlib.readthedocs.io/en/latest/component/recorder.html#record-template.
        # 投资组合回测。如果用户想要基于他们自己的自定义预测信号进行回测，
        # 请参考官方文档：https://qlib.readthedocs.io/en/latest/component/recorder.html#record-template。
        par = PortAnaRecord(recorder, port_analysis_config, "day")
        par.generate()
