# Executable Scripts Module / 量化脚本与流水线运行中心

## 📌 Introduction / 简介
本模块是 `mini_qlib` 的“控制手柄”，包含可直接在终端中运行的命令行量化脚本与数据加载流水线运行器。

---

## 🏃 Available Scripts / 可运行脚本介绍
1. **`fetch_data.py` (行情抓取与增量同步运行器)**：
   - 终端入口：`python mini_qlib/scripts/fetch_data.py`
   - 功能：自动从 Wikipedia 获取最新标普 500 成分股，检查 `mini_qlib/database/sp500.duckdb` 内已有的最新价格日期，并以增量模式（重叠 5 天，防止时区和周末遗漏）从 Yahoo Finance 抓取缺失的日频量价数据写入 `prices` 表。
2. **`fetch_edgar_runner.py` (财务报表全量抓取与断点续传器)**：
   - 终端入口：`python mini_qlib/scripts/fetch_edgar_runner.py`
   - 功能：执行标普 500 公司的 SEC 财务报表拉取全套流程。支持**断点续传**，如果中途因网络波动或手动按下 Ctrl+C 中断，再次运行本脚本会自动从上一只未完成的股票无缝继续下载，非常稳健。

---

## 🛠️ Usage / 如何开始运行
在项目根目录下激活你的 Python 虚拟环境，直接在终端中运行：
```bash
# 1. 增量抓取标普 500 最新日频行情价格
python mini_qlib/scripts/fetch_data.py

# 2. 稳健地抓取标普 500 财务基本面数据（带断点续传）
python mini_qlib/scripts/fetch_edgar_runner.py
```
> [!IMPORTANT]
> 运行前，请务必确认 `config_private.yaml` 中的 `edgar_email` 已经填写为你本人的真实电子邮箱，以确保符合 SEC 合规抓取要求！
