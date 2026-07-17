# Task Summary — v2-monthly-report(small 级,2026-07-17)

## 交付
`python -m btc_agent.report --month YYYY-MM`(report.py + test_report.py,纯新增):
① 评级统计(5 日窗,close 序列自算,尾部不足记 pending 不入分母);
② 候选分组对比(复用 settlement.counterfactual_report,账本全量口径,文案标注);
③ 虚拟账户净值回放(REPORT_PARAMS 机械仓位 {Buy:1.0,Overweight:0.5,Hold:carry,
Underweight:0.25,Sell:0},复利,0.1%/次换仓摩擦,缺日 carry 并标注)。
只读 ledger,零网络零 LLM 零新依赖。

## 一次返工(复验逮到)
初版评级统计手写 `strategy_return = sign × market_return`(Sell=-1)——ST1 刚清除的
做空口径在报表层复活。返工(809d07e):删 _DIRECTION_SIGN,改用
`rating_to_direction` + `settlement_math.spot_settle` 唯一口径;加防回归断言单测
(源码不得含自写结算式)。教训再次验证:口径只有一个 source of truth。

## 验证
- 独立复验:`subtask-summaries/main.verify.md`——ruff PASS + pytest 196 passed
  (183 既有 + 13 新增),零跳过。
- CLI 真实冒烟(读生产 ledger):exit 0,三 section 结构完整,空数据优雅,
  pending 语义正确。
- lane:small/fast——纯新增两文件,零契约面(marker 未触碰),复验+口径终审通过。

## Follow-ups
- 报表可加"推送"选项(接 push sink 每月发飞书)——等有真数据再说。
- blank_sheet 日(无 trade_levels 行)目前不计入评级统计(文档化的选择)。
