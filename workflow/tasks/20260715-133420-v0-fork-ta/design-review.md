# Design Review Gate — v0-fork-ta

- plan version reviewed: plan.md @ commit 前(4 子任务 ST1-ST4)
- round: 1

## Lens 1: Architecture Boundaries — pass(带约束)
- 单 python 组件,无前后端归属问题。子任务按职责划分(vendor / 数据 vendor / 日历 / 配置+入口),
  非按目录。ST1 显式阻塞其余。
- **约束**:ST3(日历+基准)与 ST4(LLM 配置+run)都会碰 `default_config.py` 与 `memory.py`
  (ST3 改 alpha 基准与结算窗口,ST4 加 LLM 配置与写记录)。→ ST2→ST3→ST4 **必须串行**
  (standard 本就一次一 worktree、子任务间合并),不并行,避免同源文件冲突。

## Lens 2: Contract Impact — pass
- vendor 接口 + 输出 schema 是**首次新建**,不改动既有消费者,无外部 API/IPC。
- env 假设新增 DeepSeek key(走 .env,不进 git)。contract_touchpoints/env_consistency 在 ST4 回填。
- 无 wiki(项目尚无 docs/wiki),设计文档以根目录 BTC-DESIGN-REVIEW.md 为准。

## Lens 3: Risk and Verification — pass
- 每个 ST 都能被检查矩阵验证:ST1(import+pytest)、ST2(grep 财报路由+mock 行情单测)、
  ST3(含周六的日历单测)、ST4(端到端+6 条 Acceptance)。无"trust me"子任务。
- 停止规则齐备(crypto 路径不符/依赖装不动/触实盘/DeepSeek 结构化不兼容)。
- 依赖顺序显式(ST1 阻塞;ST2-4 串行)。
- 唯一风险点:ST4 端到端要用真实 DeepSeek key。缓解:测试路径 mock LLM,真实跑为人工一次性
  确认,key 在 .env 不入库——是用户自有工具的自有 key,非安全越界。

## changes required to plan
- 在 plan 标注 ST2→ST3→ST4 串行(已在 Lens 1 说明,执行时遵守)。

## gate result: PASS(可进入子任务拆分;建议 ST1 先行,人工放行后由 task-assign 派发)
