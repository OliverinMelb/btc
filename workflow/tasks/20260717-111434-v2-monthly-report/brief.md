# Task Brief

## Goal
`python -m btc_agent.report --month YYYY-MM`:月度成绩单 CLI,三个 section——
① 月度评级统计(命中率/平均现货收益/平均 alpha);② 候选分组对比(accept vs
vetoed/observed,复用 counterfactual_report);③ 虚拟账户净值回放(可配本金,
机械仓位规则,复利口径,扣固定假设摩擦)。**只读 ledger,零网络零 LLM。**

## Context
- 数据源:`results_dir/ledger.sqlite3`(ledger.py 六表)。注意:每日评级的 5 日
  持有结算在 markdown 记忆日志里,**不在** ledger——报表的评级统计与净值回放一律
  从 ledger 自算:`snapshots.observations_json` 里有 `last_close`(regime 观察值),
  `trade_levels` 有每日 rating/direction,按 trade_date join 得到 (date, rating, close)
  序列,日收益从相邻 close 算。
- 仓位规则是机械参数(v2 红线:LLM 不出数字):模块级 `REPORT_PARAMS` dict,
  json 可序列化,含 position_weights {Buy:1.0, Overweight:0.5, Hold:"carry",
  Underweight:0.25, Sell:0.0}、friction_per_rebalance(默认 0.001)、capital 默认 1_000_000。
  Hold=维持昨仓(carry);换仓时按仓位变动比例扣摩擦。
- 缺日处理:计划任务可能漏跑,日期序列有洞时仓位顺延(carry),报表标注缺日数。
- 重叠窗口问题:净值回放用逐日复利,天然规避"重叠持有窗直接相加"的口径错误;
  评级统计 section 的"5 日命中"从 close 序列自算(t+5 无数据的尾部条目记 pending 不计入)。

## Scope
- 新增 `btc_agent/src/btc_agent/report.py`(含 `__main__` 惯例使 `-m btc_agent.report` 可跑)
- 新增 `btc_agent/tests/test_report.py`
- **禁碰其余一切**(ledger.py/settlement.py 只 import;契约 marker 文件全禁)

## Constraints
- 只读 ledger(SELECT only);无网络、无 LLM、无新依赖(stdlib sqlite3+json+argparse)。
- 输出为可读文本(推送/终端两用),金额千分位,百分比一位小数;
  明示"无摩擦仿真近似,非 v3 模拟盘"的口径注记与本月缺日数。
- 空月/无候选优雅输出(不崩,明示无数据)。

## Verification Plan(Acceptance Criteria)
- [ ] 单测:构造 ledger(tmp_path,用 ledger.py 公开 API 种数据)→ 已知收盘序列
      的净值回放结果与手算一致(含换仓摩擦、Hold carry、Sell 空仓)。
- [ ] 单测:缺日 carry 且报表标注缺日数;--month 过滤只统计当月;空月优雅。
- [ ] 单测:评级统计命中率与手算一致;尾部不足 5 日的条目不计入命中分母。
- [ ] 单测:候选 section 输出 accept vs vetoed/observed 对比(种一个 veto 已结算候选)。
- [ ] 单测:REPORT_PARAMS json 可序列化;report.py 不 import graph/intel/llm。
- [ ] btc_agent/ 内 ruff + pytest 全绿(既有 183 + 新增),零网络。

## Stop Conditions
- 发现必须写 ledger 或改 ledger schema 才能实现 → 停,报告。
- 发现 snapshots.observations_json 里拿不到 close 序列 → 停,报告(别绕道触网取价)。

## Task
v2-monthly-report

## Workflow
agent-change
