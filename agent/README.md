# Agent Module / 智能体代理与提示工程模块

## 📌 Introduction / 模块介绍
此目录位于整个工作区的根目录，专门用于存放**以大模型（LLM）为核心的 Agent 逻辑、提示词工程（Prompt Engineering）、规划逻辑及与 mini_qlib 算子引擎交互的控制代码**。

通过与项目主业务剥离，Agent 能够独立进行逻辑迭代、Prompt 测试与多 Agent 协同开发。

---

## 🚀 Core Features / 核心功能规划
1. **因子设计 Agent (Factor Designer Agent)**：
   - 接收用户的量化选股想法，自动翻译为符合 `mini_qlib` 算子语法的公式字符串（例如：“帮我设计一个收盘价向上突破20天均线的因子” -> `Gt($close, Mean($close, 20))`）。
   - 通过 `factor/whitelist.py` 对生成的因子进行安全和语法校验。
2. **研究报告 Agent (Research Agent)**：
   - 读取 `database/` 下的 PIT 真实数据以及算子的计算结果，自动对某只股票进行财务健康度诊断并生成 Markdown 研报。
3. **Prompt & Tool Templates (提示词与工具库)**：
   - 包含 LLM 专用的 system prompt、少量样本学习（Few-Shot Examples）数据、以及用于 LLM Function Calling 的算子计算工具接口定义。
