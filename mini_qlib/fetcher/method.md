# MiniQLib 数据抓取模块方法手册 (`mini_qlib/fetcher`)

本手册详细介绍了 `mini_qlib/fetcher` 目录下的所有核心文件、类、方法及函数。本模块是项目的“数据供水管道”，负责从维基百科（成分股名单）、Yahoo Finance（量K线行情价格）以及美国证券交易委员会 SEC EDGAR（高阶财务事实）拉取真实量化数据。

---

## 一、 模块概述 (Module Overview)

`mini_qlib/fetcher` 目录处理数据源对接，其核心设计逻辑为：
1. **坚固的限流与防封锁**：对于 Yahoo Finance，采用小 batch_size、批间 sleep 和“多轮分步降额重试”机制；对于 SEC EDGAR，使用符合官方规范的 User-Agent 标头和物理限速，防范 IP 封锁。
2. **对账式防静默丢失**：批量抓取行情时，自动核算“请求列表 vs 实际生成”，精准捕获缺失数据并及时警报。
3. **秒级本地缓存优先**：维基百科成分股名单等公共资源一经下载成功即缓存为本地 CSV，后续运行实现秒级无网加载。

---

## 二、 文件结构图 (File Structure)

* `get_sp_500_list.py`：负责从维基百科动态爬取标普 500 成分股基本信息并本地化缓存。
* `fetch_price.py`：负责从 Yahoo Finance 批量拉取日线历史价格，含多轮断点重试。
* `fetch_edgar.py`：负责对接 SEC EDGAR API，抓取 XBRL 规范下的三大张报表并透视为时点基本面 DataFrame。

---

## 三、 快速参考索引表 (Quick Reference Table)

| 文件名 (File) | 类名/函数名 (Class/Function) | 方法/函数签名 (Method/Function Signature) | 作用描述 (Description) |
| :--- | :--- | :--- | :--- |
| **`get_sp_500_list.py`** | `get_sp500_tickers` | `get_sp500_tickers(force_refresh=False) -> pd.DataFrame` | 获取标普 500 列表，优先加载本地缓存。 |
| | `_fetch_from_wikipedia` | `_fetch_from_wikipedia(max_retries=3) -> pd.DataFrame` | 从维基百科抓取名单，包含递增退避重试。 |
| **`fetch_price.py`** | `fetch_prices_batch` | `fetch_prices_batch(tickers, start, end, ...)` | 批量拉取行情价格（带失败对账与自动重试）。 |
| | `_download_one_batch` | `_download_one_batch(batch, start, end)` | 拉取单批股票行情，丢弃 NaN 行并堆叠为长格式。 |
| **`fetch_edgar.py`** | `get_cik_map` | `get_cik_map(headers, verify=False) -> dict` | 从 SEC 获取完整的 Ticker-to-CIK 映射表。 |
| | `fetch_company_facts` | `fetch_company_facts(cik, headers, verify=False) -> dict` | 抓取指定公司 CIK 的原始 XBRL 事实数据。 |
| | `facts_to_df` | `facts_to_df(facts, concept_map, ticker) -> pd.DataFrame` | 将原始 facts 财务细项透视为 PIT 财务表。 |

---

## 四、 核心 API 教学与防错机制 (Detailed API & Robustness)

### 1. `get_sp_500_list.py` — 成分股名单抓取

* **`get_sp500_tickers(force_refresh: bool = False) -> pd.DataFrame`**
  * **中文说明**: 获取标普 500 最新成分股基本特征（包含 symbol、security、sector、sub_industry）。
  * **三层容错设计**:
    - **第一层**：优先加载本地 `database/sp500_tickers.csv` 缓存文件（秒级返回）。
    - **第二层**：若无缓存，动态爬取维基百科，自动将 `BRK.B` 格式处理为适配 yfinance 的 `BRK-B` 破折号格式，成功后立刻自动落盘本地缓存。
    - **第三层**：若因网络连接断开抓取失败，自动打印清晰的排错文案（挂代理重试指令或手动放置 CSV 指引）。

---

### 2. `fetch_price.py` — 高抗限流价格抓取器

yfinance 批量拉取大跨度历史数据时，一旦触发限流，经常会返回含有全 NaN 的无效数据，且**默默不抛任何异常**。

* **`fetch_prices_batch(tickers, start_date, end_date, batch_size=20, sleep_between=1.5, max_retry_rounds=3)`**
  * **中文参数**:
    - `tickers`: 股票池代码列表。
    - `start_date` / `end_date`: 日期字符串。
    - `batch_size`: 每批请求的股票只数（默认 20 只，避免被 Yahoo 识别为恶意爬虫）。
    - `sleep_between`: 批间睡眠秒数（给 Yahoo 服务端喘息时间）。
    - `max_retry_rounds`: 失败股票的最大重试轮数。
  * **防遗漏对账流程**:
    1. 第一轮抓取：将所有股票按 `batch_size=20` 批次发送请求。
    2. 主动对账：每一批拉完，核对“本批本应拿到的 Tickers”与“实际拿到非空数据的 Tickers”，抓出漏网之鱼，在终端中醒目报警。
    3. 后续重试轮：针对未拿到数据的股票进行再次抓取。**重试时将 `batch_size` 自动减半（如 10、5），并相应增加停顿秒数**，直到 100% 成功或轮数用尽。

---

### 3. `fetch_edgar.py` — SEC EDGAR 财务报表抓取与 XBRL 解析

* **`get_cik_map(headers: dict) -> dict`**
  * **中文说明**: 从 SEC EDGAR 获取完整的“股票代码 ➡️ CIK（中央指数密钥，10位补零代码）”的映射表。
  * **安全提示**: `headers` 中必须按照 SEC 规范传入包含用户有效邮箱的 User-Agent 标头（如 `User-Agent: your_email@example.com`），否则会被 SEC 服务器返回 403 拒绝访问。

* **`facts_to_df(facts: dict, concept_map: dict, ticker: str) -> pd.DataFrame`**
  * **中文说明**: 将原始 XBRL 庞杂的财务数据，根据我们预设的三张表概念地图（`INCOME_CONCEPTS` 利润表、`BALANCE_CONCEPTS` 资产负债表、`CASHFLOW_CONCEPTS` 现金流量表），转换并透视为规范的 point-in-time（含有报告期末日 `period_end` 和真实物理披露日 `filed`）财务 DataFrame。

---

## 五 & 六、 初学者极速开始示例 (Quick-Start for Beginners)

以下是完整可运行的独立测试脚本，展示了初学者如何调用抓取引擎拉取名单、批量抓取股票价格并打印首尾部分：

```python
import pandas as pd
from datetime import datetime, timedelta
from mini_qlib.fetcher.get_sp_500_list import get_sp500_tickers
from mini_qlib.fetcher.fetch_price import fetch_prices_batch

# 1. 获取标普 500 最新的前 5 只股票
print("🎬 正在提取标普 500 成分股列表...")
sp500_df = get_sp500_tickers()
sample_tickers = sp500_df["symbol"].head(5).tolist()
print(f"   提取的前 5 只测试股票代码: {sample_tickers}")

# 2. 测算拉取范围（过去 30 天的历史日K线）
end_date = datetime.today().strftime('%Y-%m-%d')
start_date = (datetime.today() - timedelta(days=30)).strftime('%Y-%m-%d')

print(f"\n🎬 启动 Yahoo Finance 高抗限流批量抓取器...")
print(f"   拉取区间: {start_date} 至 {end_date}")

# 3. 运行批抓取
# 为演示对账重试性能，我们设置极小的批次 batch_size=2
df_prices = fetch_prices_batch(
    tickers=sample_tickers,
    start_date=start_date,
    end_date=end_date,
    batch_size=2,
    sleep_between=1.0,
    max_retry_rounds=2
)

# 4. 打印最终抓取结果
print(f"\n📊 行情数据抓取并长格式对齐完毕！")
print(f"   共拿到 {df_prices['ticker'].nunique()} 只股票的数据，共计 {len(df_prices)} 行量价记录。")
if not df_prices.empty:
    print("\n   前 5 行数据样板:")
    print(df_prices.head(5))
    print("\n   每只股票成功抓取的交易天数:")
    print(df_prices["ticker"].value_counts())
```
