# AGENTS.md — BTC Agent 代理协作规则

## 项目性质
BTC 情报→决策→(模拟)交易 agent，基座是 TradingAgents(LangGraph 多 agent 辩论)改装。
唯一代码组件是 `btc_agent/`(Python，src 布局，检查: ruff + pytest)。设计与路线见根目录
`BTC-DESIGN-REVIEW.md`。

## 铁律(写进代码与 prompt)
- **机械规则出候选与交易价位，LLM 只做裁决**(方向评级+理由)，绝不让 LLM 报买卖数字。
- **不让 LLM 直接下单**；v4 之前只做现货信号；执行/回测交给 freqtrade。
- **白卷文化**：环境不明确时交白卷优于硬凑。
- 涉及交易所/LLM/数据源 key 一律走 `.env`(不进 git)。

## 工作流协议
本项目用 ai-workflow 多代理协议。子代理只在分配的 worktree 内工作、只碰子任务 spec 允许的
文件；需要跨子任务改动时停下上报。实现完成后由编排者独立复验(task-verify)，不认子代理自查。

## 环境注意(详见 ~/.claude/workflow-memory/environment.md)
- 裸 `python` 是 Store 别名；用 venv 的 `.venv\Scripts\python.exe`。
- 装依赖显式 `--index-url https://pypi.org/simple`。
- 含中文的 JSON 配置存 UTF-8 with BOM；python 读这类文件用 `utf-8-sig`。
