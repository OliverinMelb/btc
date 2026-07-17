# Design Review Gate — v2-decision-card

- plan version reviewed: plan.md v1(round 1)→ plan.md v2(round 2)
- round: 2

## Round 1(plan v1)— FAIL

三并行镜头,各自结论:

- lens 1 (Architecture Boundaries) verdict: **fail** —
  F1 ST2 快照收敛未覆盖研判图 ToolNode 真实取数路径(spec AC 不可达);
  F2 结算逻辑是 TradingAgentsGraph 实例方法,ST6 无法离线复用;
  F3 编排入口"daily 或扩展 intel run"未定死,intel→graph 依赖倒挂风险;
  F4 strategy_versions schema 拆在三个子任务未定稿;F5 统计 source of truth 未声明。
- lens 2 (Contract Impact) verdict: **fail** —
  B1 plan 无回填 workflow/config.json 步骤(新模块全在契约检查覆盖面外,
  CandidateVerdict 无 structural_check,daily 入口无 env_consistency);
  B2 run.py 不变式有"检查通过但活路径旁路化"风险;B3 推送卡片缺邮件主题行/
  Telegram 4096 长度约束。
- lens 3 (Risk & Verification) verdict: **fail** —
  C1 direction_hit 未定义到可实现;legacy 口径标注会砸坏 memory.py 固定位置解析
  (`endswith("| pending]")`/fields[3]);反思闭环读旧记录混用两套 alpha;
  reflection.py 需 direction_hit 入参;C2 ST6"复用 ST1 函数"是虚假依赖
  (固定持有日 vs 事件驱动两种结算),候选结算三口径(日内触及/结算价/双触 tie-break)
  未定义;C3 ST4 编排单测未声明 fake graph 全离线,"schema 拒绝数字"不可断言;
  C4 最终端到端需真实凭据,与 stop-rules 凭据升级规则冲突,须显式留给人工。

### changes required to plan(汇总 14 条,已全部应用于 plan v2)
1. G3:ToolNode 取数不纳入本任务,spec AC 降级 + backlog v2.5。
2. G2/ST1:结算数学抽 `settlement_math.py` 纯函数;ledger/settlement 禁 import graph。
3. G1/ST4:入口定死顶层 `daily.py`;intel 不依赖 graph;candidates/ledger 注入式扩展点。
4. G5:strategy_versions DDL + params_hash 三段输入清单拆包前定稿。
5. G4:前向统计只认 ledger。
6. ST7 新增:回填 config.json(surface_markers/structural_checks/env_consistency)。
7. ST4:机械价位经由 trade_levels 既有路径,不变式延伸到 daily(ST7 落断言)。
8. ST4:卡片首行=邮件主题、Telegram 4096 截断,进单测。
9. ST1:direction_hit 完整定义(long>0/short<0/==0→False/flat→None)。
10. ST1:legacy 标注机制——pending 行不动,已结算 tag 尾部追加可选字段,
    `_parse_entry` 按字段数容错;读取侧标注 (legacy short-basis)。
11. ST1:reflection.py 签名扩展,direction_hit 穿透。
12. ST6/G6:事件驱动结算器新写;四口径(日内触及即算/按触及价位结算/
    双触保守判失效先/到期收盘)全入 settlement_params 进版本 hash。
13. ST4/ST5 单测:fake graph+fake snapshot 全离线;CandidateVerdict 改为
    "无数值类型字段"可断言形式(spec 同步修订)。
14. G7:真数据端到端由人工/主会话执行,不派 implementer,不进 verify 矩阵。

## Round 2(plan v2)— 复审

- lens 1 verdict: pass — A1-A4 全落实,代码抽查(trading_graph.py:294-300 可抽出、
  依赖方向单向)确认可行。
- lens 2 verdict: pass — B1-B3 全落实;ST7 新断言只增不改,不误伤现有检查。
- lens 3 verdict: pass — C1-C4 全落实;memory.py 解析容错、High/Low 可用性、
  reflection 入参扩展点均经代码核实。
- 不阻塞备注:
  (a) brief Scope 第 2 条措辞与 G3 降级有出入 → 已在 brief 补 G3 注记;
  (b) ST7 的 daily.py 白卷关键字与 ledger 只读不变式的具体字面量,
  须在 ST4/ST6 实现落地后、ST7 回填前定死(执行序已保证)。

- gate result: **PASS**(proceed to subtask split)
