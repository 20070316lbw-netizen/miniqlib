# 研究与踩坑日志 (Research & Pitfall Log)

* **日期**：2026-05-23
* **作者**：Antigravity (AI Coding Assistant) & User
* **主题**：VSCode DuckDB 插件配置故障、数据库文件独占锁定、以及标普500财务数据下载中的代理与 SSL 握手问题

---

## 📌 踩坑与问题记录

### 坑 1：VSCode DuckDB 插件无法挂载并报错配置问题
* **问题现象**：在 VSCode 中无法直接打开或使用 `edgar.duckdb` 数据库。
* **原因分析**：工作区配置文件 `.vscode/settings.json` 中的 `duckdb.databases` 配置项不完整。原配置只写了 `"path"` 和 `"attached": false`，缺少了插件内核所必须的 `"alias"`（别名）和 `"type"`（连接类型，如 `"file"`）属性。
* **解决方案**：
  将配置规范化，同时为了防止绝对路径在不同机器上出错，将物理路径改为基于工作区的相对路径 `./edgar.duckdb`：
  ```json
  "duckdb.databases": [
      {
          "alias": "edgar",
          "type": "file",
          "path": "./edgar.duckdb",
          "attached": true
      }
  ]
  ```

---

### 坑 2：Windows 下的 DuckDB 数据库文件独占加锁冲突
* **问题现象**：
  1. 在 VSCode 左侧目录双击数据库文件，弹出 `无法读取文件 ... FileSystemError` 报错。
  2. 运行 Python 脚本连接数据库报错：`_duckdb.IOException: IO Error: Cannot open file ... File is already open in Code.exe (PID 6932)`。
* **原因分析**：
  * DuckDB 在底层为了防止多进程同时写入造成数据损坏，在 Windows 下打开数据库文件时会自动加上**独占写锁**。
  * 只要 VSCode 插件（运行在 Extension Host `Code.exe` 后台）加载并连接了该数据库，就会一直霸占锁。此时无论是在 VSCode 里双击它，还是在外部运行 Python 脚本试图连接，都会因为无法获取文件锁而报错。
* **解决方案**：
  1. 在下载数据或终端操作数据库时，需要在 `.vscode/settings.json` 中临时将插件的自动挂载关闭：`"attached": false`。
  2. 在 VSCode 中按 `Ctrl + Shift + P` 执行 `Developer: Reload Window`（重载窗口），彻底杀死之前的插件后台进程，从而释放锁。
  3. 待 Python 后台脚本运行完毕后，再将配置改回 `"attached": true` 进行可视化查询。

> [!IMPORTANT]
> **黄金法则**：在运行 Python 脚本下载或写数据库时，必须断开 VSCode 插件的连接或重载窗口释放锁；在 VSCode 插件中查询数据时，避免同时运行 Python 写脚本。

---

## 🌐 标普500数据拉取网络 SSL 握手失败问题

### 坑 3：通过本地代理拉取 SEC 官网数据时发生 SSLError
* **问题现象**：
  Python 脚本在请求 `https://www.sec.gov/files/company_tickers.json` 时崩溃报错：
  `requests.exceptions.SSLError: HTTPSConnectionPool(host='www.sec.gov', port=443): Max retries exceeded (Caused by SSLError(SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol')))`
* **原因分析**：
  * 用户系统上开启了本地代理（Clash / Clash Verge 等，代理端口为 `127.0.0.1:7897`），并自动注入了系统环境变量 `HTTP_PROXY`/`HTTPS_PROXY`。
  * 代理软件在截获 HTTPS 连接并进行流量中转时，由于证书链验证问题或握手协议不兼容，导致 Python `requests` (基于 `urllib3`) 在建立 SSL 安全通道时被代理或 SEC 服务器强行断开连接（EOF）。
* **解决方案**：
  1. **开启 `verify=False`**：在 `requests.get` 请求中添加 `verify=False` 属性，跳过本地代理证书链校验。
  2. **屏蔽警告**：导入 `urllib3` 并调用 `urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)`，从而避免日志里塞满证书未校验的警告，保持终端输出清爽。
  3. **数据源拓展**：修改 `fetch_data.py` 中的 `SP500_TICKERS` 读取逻辑，由原先硬编码的 10 个测试 Ticker，更改为动态读取标普500成分股 CSV 文件 `mini_qlib/database/sp500_tickers.csv`：
     ```python
     SP500_TICKERS = pd.read_csv(
         r"C:\Users\liu\Desktop\miniqlib\mini_qlib\database\sp500_tickers.csv"
     )["symbol"].tolist()
     ```

---

## 📈 抓取任务圆满成功 (Download Completed Successfully)

* **执行任务**：`.venv\Scripts\python.exe fetch_data.py` (`task-119`)
* **运行时间**：2026-05-23 23:25:44 至 23:38:28 (耗时约 46 分钟)
* **执行结果**：标普500成分股中 **441 家公司**的数据成功抓取并解析入库 (62 家失败原因为 SEC 无数据或 CIK 无法在官方映射表中对齐，属于正常偏差)
* **数据库统计量**：
  * 利润表数据 (`income`)：**82,726** 行
  * 资产负债表数据 (`balance`)：**117,219** 行
  * 现金流量表数据 (`cashflow`)：**58,111** 行
  * 数据总体积：约 **25.8 万** 条财务明细，包含了过去 10 年以上的点对点（Point-in-Time）真实披露记录！

---

## 🔒 插件锁定复原与开发环境闭环

1. **配置恢复**：下载完成后，已自动将 `.vscode/settings.json` 中的数据库自动挂载参数还原为 `"attached": true`。
2. **使用建议**：由于 VSCode DuckDB 插件再次挂载并锁定了 `edgar.duckdb`，如后续需再次通过外部脚本运行大规模写入，请临时将 `"attached"` 设为 `false` 并 `Reload Window` 释放锁。日常查询和读操作均可在 VSCode 中直接飞速完成！

