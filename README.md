# 智能问数 Agent

> 由 devflow 初始化生成，请按实际项目补充。

## 项目简介

面向实习作品场景的智能问数 Agent：用户用自然语言查询电商经营数据，系统通过 NL2SQL 生成待确认 SQL，并结合 RAG 回答指标口径类问题，同时提供安全校验、拒答和可量化评估。

## 交付路线

- 需求与验收标准：`docs/requirements/REQ-001-chatbi-agent.md`
- 六周 WBS 与里程碑：`docs/plan/PLAN-001-six-week-mvp.md`
- 当前阶段与任务状态：`python tools/devflow/devflow.py status`

## 技术路线

- 后端：Java 17+、Spring Boot、Spring AI 或 LangChain4j
- 存储：MySQL、Redis、PGVector / 嵌入式向量存储
- 核心链路：Function Calling、NL2SQL、RAG、SQL 安全校验、审计与评估
- 部署：Docker Compose

## 本地开发

```bash
# 查看当前流程阶段与全景状态
python tools/devflow/devflow.py status

# 校验当前阶段是否满足准出契约（CI 执行同一套命令）
python tools/devflow/devflow.py check
```

## 文档

完整交付物与流程见 [docs/README.md](docs/README.md)：

- 需求：`docs/requirements`
- 设计：`docs/design`、`docs/adr`
- 排期：`docs/plan`
- 评审：`docs/review`
- 测试：`docs/test`
- 发布：`docs/release`
- 复盘：`docs/retro`

## 提交规范

分支：`feature/<需求号>-<简述>`、`fix/<需求号>-<简述>`、`release/vX.Y.Z`
提交：`<type>(<scope>): <简述>`，type ∈ feat / fix / docs / refactor / perf / test / build / ci / chore / revert

## 发布

版本记录见 [CHANGELOG.md](CHANGELOG.md)。项目流程状态存放在 `.devflow/`（务必随代码提交）。
