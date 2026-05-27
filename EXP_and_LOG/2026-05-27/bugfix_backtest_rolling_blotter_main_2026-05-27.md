# MiniQLib Bugfix Log: Backtest/Operator/EntryPoint 修复记录

**日期**：2026-05-27  
**作者**：Codex Agent  
**范围**：`mini_qlib/backtest`、`mini_qlib/data`、`main.py`

## 修复概览

### 1) 回测买入估算价与撮合价不一致（Bug 1）
- 问题：策略侧使用 T 日 close 估算买入股数，但撮合用 T+1 open（含滑点），在跳空场景下系统性偏离目标仓位。
- 修复：
  - 在下单时把“目标补仓金额（target_cash）”随订单携带。
  - 在 Exchange 成交前基于真实成交价 `fill_price` 再次约束 `fill_volume <= target_cash / fill_price`。
- 效果：在高开缺口时防止过度买入，在低开缺口时保持保守，不再仅依赖现金降额兜底。

### 2) Rolling 默认 `min_periods=1` 语义偏差（问题 3）
- 问题：`Mean($close, 10)` 前 1~9 天提前出值，语义不再是“10日均线”；短窗指标早期噪声偏高。
- 修复：
  - `Rolling._DEFAULT_MIN_PERIODS` 从 `1` 改为 `None`。
  - 在 `Rolling.__init__` 内将 `min_periods is None` 解释为 `min_periods = N`（N>0）。
- 效果：默认行为与常见技术指标语义一致；如需旧行为可显式传 `min_periods=1`。

### 3) Blotter 已实现盈亏记录缺失（问题 5）
- 问题：卖出清仓后直接删除持仓，未记录 realized PnL。
- 修复：
  - 新增 `Blotter.realized_pnl` 字段。
  - 在 SELL 成交时按 `matched_volume * (fill_price - cost_price) - commission` 累加。
- 效果：保留后续归因分析所需的已实现收益轨迹。

### 4) main.py 空壳入口（设计建议 2）
- 问题：入口只打印 Hello，和实际 pipeline 脱节。
- 修复：`main.py` 转发到 `mini_qlib.scripts.run_pipeline.main()`。

## 未在本轮直接改动但已确认
- `Ref.get_extended_window_size` 对负 N 的公式本身成立；真正缺口在 DataHandler 尚未消费该窗口信息（边界 NaN 由 dropna 吃掉）。本轮先不做破坏性重构。
- 标签归一化泄露风险属于“即将实现的 label_processors 设计点”，建议在 split 后仅 fit train，再 transform valid/test。

## 回归建议
1. 新增跳空行情场景下的回测单测（验证 target_cash 约束）。
2. 为 Rolling 算子新增默认语义测试（MA10 前 9 天应为 NaN）。
3. 给 Blotter 增加 realized_pnl 校验测试。
