# 智能问数 Agent 文档索引

> 由 devflow 自动生成于 2026-10-24。新增交付物后请补录到对应阶段，
> 否则 `doc.index` 规则会标红（可本地执行 `devflow check` 验证）。

## 快速开始

```bash
 tools/devflow/devflow.py status      # 看全景
 tools/devflow/devflow.py check       # 校验当前阶段准出
 tools/devflow/devflow.py gate        # CI 用的严格门禁
```

## 阶段与产出物

| 阶段 | 目标 | 产出物目录 | 必需交付物 |
| --- | --- | --- | --- |
| 1 intake 需求立项 | 收敛需求、定义验收标准 | `docs/requirements` | 需求说明书 REQ-* |
| 2 design 方案设计 | 技术方案与架构决策 | `docs/design`、`docs/adr` | 技术方案 DESIGN-*、ADR-*（可选） |
| 3 plan 排期计划 | WBS 拆解与里程碑 | `docs/plan` | 排期计划 PLAN-* |
| 4 develop 开发执行 | 分支/提交规范与编码 | 代码仓库 | 符合规范的分支与 commit |
| 5 review 代码评审 | 结构化评审与意见闭环 | `docs/review` | 评审记录 REVIEW-* |
| 6 test 测试验证 | 用例、覆盖率与缺陷清零 | `docs/test` | 测试计划 TEST-* |
| 7 release 发布部署 | 灰度上线与回滚就绪 | `docs/release` | 发布计划 RELEASE-* |
| 8 retro 复盘归档 | 量化复盘与改进回流 | `docs/retro` | 复盘报告 RETRO-* |

## 交付物清单

<!-- devflow:index:start -->
<!-- 本段由 devflow 自动生成，修改请提交流程命令 -->

| 编号 | 类型 | 标题 | 路径 |
| --- | --- | --- | --- |
| REQ-002 | requirement | 权限执行与模型接入(二期) | [docs/requirements/REQ-002-permission-llm.md](../docs/requirements/REQ-002-permission-llm.md) |
| PLAN-002 | plan | REQ-002 权限与模型接入排期 | [docs/plan/PLAN-002-req-002.md](../docs/plan/PLAN-002-req-002.md) |
| DESIGN-001 | design | 权限执行与模型接入设计 | [docs/design/DESIGN-001-design.md](../docs/design/DESIGN-001-design.md) |

<!-- devflow:index:end -->

## 状态快照

- 机器可读状态：`.devflow/state.json`
- 事件日志：`.devflow/log.jsonl`
- 全景报告：`.devflow/STATUS.md`
- 流水线平台：github
