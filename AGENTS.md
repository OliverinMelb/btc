# BTC Agent 协作指南

## 项目定位

这是基于 TradingAgents（LangGraph 多 agent 辩论、记忆与反思闭环）改造的 BTC 信息检索、决策和模拟交易项目。主要 Python 代码位于 `btc_agent/`，采用 `src` 布局。

动手前按任务阅读：

- `BTC-AGENT-FEASIBILITY.md`：可行性调研与 v1-v4 路线。
- `BEACON-FEATURE-REFERENCE.md`：产品功能拆解参考。
- `BTC-DESIGN-REVIEW.md`：设计评审、修订和 v0 改造清单；实现以此为准。

## 核心原则

- 机械规则生成候选与交易价位；LLM 只做方向评级和理由裁决，禁止让 LLM 直接给出买卖数字。
- 环境不明确时优先交白卷，不为产生信号而强行判断。
- LLM 不直接下单。v4 之前只产生现货信号；执行和回测交给专用交易系统。
- 用反事实归因和策略版本状态机（实验、前向验证、已验证）证明价值，不依赖主观感觉。
- 交易所、LLM 和数据源密钥只放 `.env`，不得提交或输出。

## 开发与验证

- 优先使用 `btc_agent\.venv\Scripts\python.exe`，不要依赖 Windows Store 的裸 `python` 别名。
- 在 `btc_agent/` 内按项目配置运行 Ruff 和 pytest；先跑受影响测试，再跑完整检查。
- 网络库不一定继承浏览器代理。涉及交易所访问时，按库要求显式配置并先验证当前本机代理端口。
- 本机通用环境说明见 `C:\Users\admin\.agents\workflow-memory\environment.md`。

## 工作方式

- `workflow/` 是 Codex Workflow v1 的项目配置、任务包和证据目录。非微型任务调用 `$codex-workflow`，由任务分级决定是否创建任务包或使用子代理。
- 旧 Claude Code 的 `/ai-workflow:*` 命令仅作历史参考，不在 Codex 中调用。
- 使用 Codex 原生 worktree 和 agent 能力。修改前先检查分支与脏文件，严禁覆盖无关的用户改动。
- 未经用户明确授权，不执行真实交易、部署或其他外部状态变更。

<!-- codex-workflow:project-conventions:start -->
## Agent skills

### Issue tracker

Local Markdown issues are stored under `.scratch/<feature>/issues/`. Publication policy is `explicit`. See `docs/agents/issue-tracker.md`.

### Domain docs

Use the `single` domain layout. See `docs/agents/domain.md`.
<!-- codex-workflow:project-conventions:end -->
