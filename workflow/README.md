# Workflow 层（BTC Agent）

本项目使用 ai-workflow 多代理协议。引擎(脚本/hooks/skills)在 ai-workflow plugin 中，
本目录只承载项目特定的"数据"：`config.json`（组件/检查/工作流分级）、`templates/`、
`checks/`、`context/lessons.md`、任务包(`tasks/`)。

协议详情见 plugin README。常用入口：`/task-new`（新需求分级路由）、`/task-assign`
（开 worktree 派实现子代理）、`/task-verify`（独立复验）、`/task-close`（闭环收尾）。
