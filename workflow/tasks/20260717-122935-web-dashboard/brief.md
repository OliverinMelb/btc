# Task Brief

## Goal
BTC agent Web 仪表盘:静态站点(`web/`)+ 数据导出器,Vercel 部署,daily 计划任务
跑完自动导出+push 触发重部署。分级:small(导出器与 report.py 同构只读;前端纯新增)。

## Context
- 数据源只有 ledger.sqlite3(只读),复用 report.py 的统计函数(评级统计/NAV 回放/
  反事实)——**不得**再写第三套结算数学(见 lessons:口径唯一真源 spot_settle)。
- 部署形态:整个 btc 私有仓库上 GitHub,Vercel Root Directory=web/(纯静态,无构建)。
- 数据更新链:run_daily.cmd 成功后 → `python -m btc_agent.webexport` 写
  `web/data/dashboard.json` → git commit+push → Vercel 自动重部署。

## Deliverables
1. `btc_agent/src/btc_agent/webexport.py`:导出 dashboard.json——
   近 90 天 (date, close, regime, rating, blank_sheet)、NAV 回放序列(复用 report 的
   回放函数,如需拆"返回序列"做最小重构但口径函数不动)、候选列表(含裁决/结算/价位)、
   反事实汇总、评级统计、generated_at_utc。零网络,只读 ledger。
2. `web/index.html`(+内联或同目录 css/js):中文界面,深浅色自适应——
   顶部:最新一日卡片摘要(环境/评级/白卷/关注位/证据完整度);
   图 1:收盘价+环境色带时间线;图 2:虚拟账户净值 vs BTC 持有基准;
   表:候选记录(类型/裁决/入场/失效/目标/结算结果);反事实对比块;月度统计块。
   无框架无构建(vanilla JS + 内联 SVG 图),fetch ./data/dashboard.json 渲染;
   数据缺失时优雅显示"暂无数据"。
3. `web/vercel.json`(如需要;纯静态其实可零配置)+ `deploy/run_daily.cmd` 追加
   导出+push 步骤(push 失败只告警不影响 daily 退出码语义)。
4. 上传:gh 建私有仓库 OliverinMelb/btc → push master → vercel 部署 web/。

## Acceptance Criteria
- [ ] webexport 单测:构造 ledger → JSON 字段齐全/日期序正确/空库优雅;
      不 import graph/intel/llm;json 可解析。
- [ ] 真实账本冒烟:webexport 跑出的 dashboard.json 非空且 index.html 本地打开可渲染。
- [ ] ruff + pytest 全绿(既有 199 + 新增)。
- [ ] GitHub 私有仓库存在且 master 已 push;Vercel 生产部署返回 200。
- [ ] .env/凭据类文件确认不在仓库(gitignore 已覆盖,push 前复查)。

## Stop Conditions
- 需要把 ledger/凭据传到任何云端服务 → 停(数据只以导出 JSON 形式发布)。
- gh 登录需用户交互 → 停下来等用户跑 `! gh auth login`。

## Task
web-dashboard

## Workflow
agent-change
