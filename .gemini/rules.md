# Agent Rules / 智能体规则

- **Default Language / 默认语言**: Always communicate in Chinese (zh-CN) by default. (默认使用中文与用户交流)

- **Experiment & Issue Logging / 实验与问题记录规范**:
  无论是在开发中遇到了技术问题、做出了架构重构、纠正了设计误区，还是记录了实验数据，都必须在根目录的 `EXP_and_LOG/<YYYY-MM-DD>/` 文件夹（以当天日期命名）下新建 Markdown 文件进行详细记录。
  * 记录内容应包括：遇到的问题/发现的现象、深度原因分析、对比方案、最终的解决办法/系统架构设计。
  * 这样能保证所有重要的工程决策、实验结论和踩坑记录被长期沉淀，方便后续对话及其他智能体阅读。
