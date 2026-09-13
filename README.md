# GameOps Investigator

> **English overview** — Investigate tutorial drop-off, cohort churn, and duplicate tracking events with read-only SQL and statistical comparisons. Generate reports with ranked cause candidates, supporting queries, and findings for analyst review. Built with synthetic game data; supports Claude Code through MCP and a deterministic replay mode for offline use.
>
> [Architecture](docs/architecture.png) · [Demo GIF](docs/demo.gif) · [Security boundary](docs/SECURITY.md) · [Onboarding](docs/ONBOARDING.md) · [Evaluation cases](evals/cases.jsonl)

用于排查教程掉点、分群流失和重复埋点的游戏数据调查工具。它通过只读 SQL、分群对比和统计检验整理候选原因，生成附有查询证据、限制说明和待复核结论的报告。

Claude Code 负责规划排查步骤与解释结果；指标计算、SQL 执行、分群比较、异常检测和引用校验由确定性程序完成。

> 数据声明：仓库内是固定种子生成的 5,000 名合成玩家和 136,164 条源事件。三个事故仅注入派生数据库，不代表真实商业游戏指标。

![Architecture](docs/architecture.png)

![Investigation workbench demo](docs/demo.gif)

## 调查流程与示例

`指标告警 -> Claude/回放协调器制定排查计划 -> MCP 工具调用 -> SQL 与分群下钻 -> 原因 Top-3 + 证据 -> 人工复核报告`

内置三个可复现案例：

1. 教程关键步完成率下降，D1 留存同步下滑。
2. `leveraged` 玩家分群流失，整体检验未越过阈值但分群显著。
3. `system_opened` 重复上报，事件级强度虚高而玩家级采用率基本稳定。

工作台提供调查结论、完整工具调用记录、只读 SQL 沙盒和维度下钻图，也可查看 40 条固定评测及安全边界说明。

查看一份已生成的[教程掉点调查报告](reports/tutorial_failure.md)：报告列出告警变化、三个候选原因及其依据，并保留 SQL、证据 ID 和后续检查建议。对应的[工具调用记录](reports/tutorial_failure.trace.json)可用于核对调查过程。

## 一键运行（Windows）

```powershell
.\setup.ps1
.\run.ps1
```

浏览器打开 [http://localhost:8501](http://localhost:8501)。`setup.ps1` 会创建项目级 `.venv`，安装依赖、重建事故数据、生成三份报告、运行测试和 40 条评测。

如果环境已配置，只启动界面：

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
```

## Claude Code + MCP

仓库根目录的 `.mcp.json` 会注册 `gameops` stdio 服务器。`setup.ps1` 会在仓库 `.tools/` 下安装便携式 Claude Code（不改系统 PATH）；首次使用时完成一次交互式登录，然后：

```powershell
.\claude-local.ps1 mcp list
.\.venv\Scripts\python.exe -m gameops_investigator.cli claude "Investigate the tutorial failure alert."
```

Claude 调查超时或本地程序无法启动时，返回 `ok: false` 和 `error_code`（`timeout` / `launch_failed`），CLI 退出码为 `1`。错误提示不包含异常中的原始问题、路径或部分输出，也不会自动重试。超时可缩小调查问题后手动重试；启动失败则检查本地安装和执行权限。工作台下方的确定性回放不代表本次 AI 调查成功。这些异常分支通过模拟进程测试验证，不代表已完成真实模型质量评测。

Claude Code 可调用五个工具：

- `get_metric_definition`：指标口径、埋点、负责人和质量注意事项。
- `query_metrics`：受校验的只读 SQL，表白名单、行数和超时限制。
- `compare_cohorts`：版本、渠道、活动或玩家分层的确定性比较。
- `detect_anomalies`：两比例 z 检验或对数率比检验。
- `draft_incident_report`：带 SQL、证据 ID、置信度、限制和人工复核状态的报告。

Streamlit 默认使用 `Deterministic replay`，按固定流程调用同一套工具，无需 Claude 登录即可运行演示、测试和离线评测。Claude 模式需要完成登录。

也可以从命令行执行同一套只读查询，并按演示场景收紧返回行数和超时：

```powershell
.\.venv\Scripts\python.exe -m gameops_investigator.cli query "SELECT user_id FROM users ORDER BY user_id" --row-limit 25 --timeout-ms 1000
```

`--row-limit` 允许 `1–500`，`--timeout-ms` 允许 `50–10000`；越界输入会由查询安全层拒绝。结果中的 `truncated` 会准确标记是否因安全行数上限而省略了更多记录。

行数上限只限制最终返回的记录，不会改写子查询或 CTE 中的 `LIMIT`，因此不会改变抽样范围、计数或聚合结果。`executed_sql` 保留实际执行的原 SQL（去除首尾空白）；详细例子见 [查询语义与返回上限](docs/SECURITY.md#query-semantics-and-result-limits)。

CLI 将工具结果（包括 `ok: false` 的错误）以 JSON 写入标准输出。成功时退出码为 `0`，工具返回失败时为 `1`，命令行参数格式错误时为 `2`（用法提示写入标准错误）。PowerShell 脚本可检查 `$LASTEXITCODE`，避免把被拒绝的查询当作成功执行。

## 结果与评测

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe evals\run_evals.py
```

默认结果写入 `artifacts/eval_results.json`。这里的分数是 **deterministic offline baseline**：验证固定题集、工具函数、回放协调器、安全策略和引用校验，不是 Claude 模型分数。

记录项包括：

- 工具选择准确率；
- SQL 安全策略预期结果率；
- 原因候选 Top-3 命中率；
- 报告引用准确率；
- 本地 p50 / p95 延迟；
- Claude Code 运行状态与成本边界。

同一轮评测中，归因与治理检查复用同一场景的调查结果；下一轮重新计算。p50 / p95 是各测试用例的耗时，包含缓存命中，不代表独立调查的端到端延迟。Claude 模式的工具选择、归因、成本和延迟需通过已认证运行单独测量。

评测 JSON 中的运行状态只保留必要摘要，不写入本机程序路径、认证诊断或原始模型输出。可选的 `--claude` 运行也只记录成功与否、耗时和退出码，不产生模型评分；SQL 错误使用固定类别。排查具体错误时，请在本机运行对应工具。详见 [评测导出边界](docs/SECURITY.md#evaluation-exports)。

## Agent 调用轨迹检查

除了检查报告，还可以离线检查一次调查的工具调用顺序、成功状态与调用次数：

```powershell
.\.venv\Scripts\python.exe -m gameops_investigator.cli audit-trace reports/tutorial_failure.trace.json
```

检查器会标出未先读取指标定义、缺少查询或检测步骤就生成报告、未知工具、调用失败和预算超限。它不执行轨迹里的任何内容，也不需要模型 API。现有样例来自确定性回放；通过检查不代表模型回答正确或证据真实。输入格式、规则与参考项目见 [Agent 轨迹审计说明](docs/AGENT_TRACE_AUDIT.md)。

## 接入其他游戏

核心代码不依赖 Newton 的玩法文案。接入另一款游戏需要：

1. 将仓库表映射到 `config/schema_contract.json` 的 `users` / `events` 最小模型；
2. 在 `config/metrics.json` 添加留存、漏斗、用户采用率、事件强度或数据质量指标；
3. 在 `config/scenarios.json` 添加告警窗口和下钻维度；
4. 为新指标补固定评测。

现有查询校验、MCP 接口、统计检测、证据记录、报告引用校验和评测框架可继续使用。详见 [接入指南](docs/ONBOARDING.md) 与 [安全边界](docs/SECURITY.md)。

## 项目结构

```text
app.py                     Streamlit 工作台
gameops_investigator/      核心包与 MCP 服务
config/                    指标、场景和数据契约
data/source/               不可改源快照
scripts/                   数据注入、报告和架构图生成
prompts/                   规划、指标解释、报告模板
evals/                     40 条固定评测与评分器
reports/                   三个事故报告和完整 trace
docs/                      架构、安全、接入与演示脚本
tests/                     单元与集成测试
```

## 项目归属与许可

这是一个在 AI 辅助下开发的个人项目（AI-assisted），用于探索游戏数据调查流程、MCP 工具接入和报告生成。

- 软件代码采用 [MIT License](LICENSE)。
- `data/source/` 中的合成数据采用 [CC BY 4.0](DATA_LICENSE.md)。
- `.tools/`、`.venv/`、Claude 登录状态及本地密钥不会进入版本库。
