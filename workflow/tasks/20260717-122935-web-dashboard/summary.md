# Task Summary — web-dashboard(small 级,2026-07-17)

## 交付
- `btc_agent/src/btc_agent/webexport.py`:只读 ledger → `web/data/dashboard.json`
  (近 90 天日线/环境/评级、全窗口 NAV 回放、候选+裁决+结算、反事实、月度统计)。
  回放公式经最小重构复用 `report.replay_dates` 唯一真源;5 个新单测含防回归断言。
- `web/index.html`:中文单文件仪表盘(vanilla+内联 SVG,深浅色自适应):最新决策卡
  摘要 tiles、收盘价+环境色带图、净值 vs BTC 持有图(十字线 tooltip)、月度评级统计、
  候选表、反事实对比。色板用 dataviz 参考实例,明暗两套过 validate_palette(浅色
  aqua 对比 WARN 由图例+tooltip+表格 relief 兜底)。
- 部署链:GitHub 私有仓库 `OliverinMelb/btc`(master 已 push,push 前复查无敏感文件,
  .env gitignore);Vercel 项目 `btc-dashboard`(Root=web/,纯静态),生产 URL
  https://btc-dashboard-five-flax.vercel.app (index/data 均 200)。
- `deploy/run_daily.cmd`:daily 成功后 webexport → git push → `vercel deploy --prod`
  (GitHub 集成 CLI 连接失败——需浏览器装 Vercel GitHub App,故用 CLI 直部;
  三步任一失败仅 WARN 日志,不改 daily 退出码)。

## 验证
- 独立复验 `subtask-summaries/main.verify.md`:ruff PASS + pytest 204 passed。
- 真实数据导出冒烟:dashboard.json 3 天数据字段齐全。
- 生产验证:Invoke-WebRequest index 200 / data 200(本机 curl 因代理 SSL 报错,
  非站点问题)。

## Follow-ups
- 可选:浏览器装 Vercel GitHub App 后 `vercel git connect`,即可移除 cmd 里的 CLI 直部。
- 明天 08:30 首次全自动链路(daily→导出→push→deploy),值得看一眼 scheduler 日志。
