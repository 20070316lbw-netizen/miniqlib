# Data Fetcher Module / 数据抓取与网络解析

## 📌 Introduction / 简介
本模块是 `mini_qlib` 的“源头活水”，负责从各种公共金融数据源（如 SEC EDGAR、Yahoo Finance、Wikipedia）安全、合规且稳健地抓取原始数据，并提供结构化预处理。

---

## 📂 Core Fetchers / 核心抓取器职责
1. **`fetch_edgar.py` (SEC EDGAR 财务报表抓取与 XBRL 解析)**：
   - 自动获取标普 500 成分股的最新 CIK 映射表。
   - 解析 SEC API 报送的复杂 `XBRL Facts` JSON 文件。
   - 将原始 XBRL 数据智能清洗、过滤，透视为行级的 Point-in-Time 格式，并写入 DuckDB 的 `income`、`balance`、`cashflow` 表中。
   - 严格遵循 SEC 限速要求，带有智能重试机制和断点续传（通过 `download_log` 校验）。
2. **`fetch_price.py` (Yahoo Finance 日频行情抓取)**：
   - 借助 `yfinance` 等高效的网络 API，批量并发拉取标普 500 成分股的完整日频行情量价数据。
   - 自动对异常极值、交易停牌或空数据进行补充与平滑。
3. **`get_sp_500_list.py` (标普 500 权重列表抓取)**：
   - 从 Wikipedia 抓取最新的标普 500 股票代码、行业分类以及 CIK 基础信息，导出到 `database/sp500_tickers.csv` 中作为整个系统的基础股票池（Stock Pool）。

---

## 🚦 Compliance & Safety / 合规与限速规范
* **SEC EDGAR 限速要求**：SEC 官方要求每个 IP 访问频次不得超过 **10次/秒**，且请求 Header 必须声明合法的 `User-Agent`（包含可识别的邮箱）。我们的 `fetch_edgar` 通过在 `config_private.yaml` 读取你的邮箱，并加上严格的 `RATE_LIMIT = 0.12` 限速延迟，完美达成了合规抓取，防止 IP 被 SEC 官方临时屏蔽。
