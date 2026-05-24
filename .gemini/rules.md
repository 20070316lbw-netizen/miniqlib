# Agent Rules / 智能体规则

- **Default Language / 默认使用中文**: 默认使用中文（zh-CN）与用户交流。

- **File Header Architecture Diagrams / 文件顶部架构图规范**:
  每个核心代码文件（包括算子引擎、基类地基、工具模块等）的顶部，必须包含一个用 ASCII/文本字符绘制的清晰架构/流程关系图。
  * 架构图需清晰展示该文件的核心类继承关系、数据流动方向或方法调用链路。
  * 使得代码在视觉上极具表现力，且极度便于后续开发与智能体快速理解。

- **Experiment & Issue Logging / 踩坑与实验记录**:
  遇到技术瓶颈、架构重构、纠正设计误区或记录实验时，必须在 `EXP_and_LOG/<YYYY-MM-DD>/` 下新建 Markdown 记录。
  * 记录应包含：问题现象、原因深度分析、方案对比、最终架构决策。

- **Language for Reports & Artifacts / 工件语言**:
  所有生成的实施计划、任务列表、工作梳理及报告工件（Artifacts），必须默认使用中文（zh-CN）编写。

- **Bilingual Code Comments / 双语注释并重**:
  代码的注释应尽可能遵循中文与英文并行的原则，并参考 `translator.md` 的规范，以保证代码的国际化友好度与可读性。