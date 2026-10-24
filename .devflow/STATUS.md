# 智能问数 Agent 项目管控全景

> 本文件由 devflow 自动生成，请勿手工编辑；修改请落到 `devflow.yaml` 与流程命令。

- 项目：智能问数 Agent
- 当前阶段：**develop**
- 最近更新：2026-10-24T08:07:21
- 已完成阶段：intake、plan

## 当前阶段目标

**4.0 · 开发执行**：按分支与提交规范完成编码、自测和 PR 提交，满足合入门禁

下一步：
- 创建符合规范的分支与 PR：`feature/<需求号>-<简述>`
- 运行 `devflow new review --title "XXX 代码评审"` 进入评审阶段

## 阶段进度

| # | 阶段 | 状态 | 进入时间 | 完成时间 | 最近校验 |
| --- | --- | --- | --- | --- | --- |
| 1 | [x] intake | 已完成 需求立项 | 2026-10-24T03:47 | 2026-10-24T03:50 | 通过 (0E/1W) |
| 3 | [x] plan | 已完成 排期计划 | 2026-10-24T03:50 | 2026-10-24T03:51 | 通过 (0E/0W) |
| 4 | [~] develop | 进行中 开发执行 | 2026-10-24T03:51 | - | 通过 (0E/1W) |
| 5 | [ ] review | 未开始 代码评审 | - | - | - |
| 6 | [ ] test | 未开始 测试验证 | - | - | - |
| 7 | [ ] release | 未开始 发布部署 | - | - | - |

## 最近一次门禁结果

**结论**：通过（错误 0 / 警告 1 / 提示 0，运行规则 7 条，模式 `warn`）

| 级别 | 规则 | 问题 | 位置 | 修复建议 |
| --- | --- | --- | --- | --- |
| 警告 | `repo.tree_clean` | 有 2 处未提交改动，例如：M .devflow/log.jsonl | - | `git add -A && git commit -m "chore: ..."`；若某文件是生成产物，可加入 devflow.yaml#repo.clean_ignore |

## 任务与排期

总数 15 ｜ 完成 12 ｜ 进行中 0 ｜ 阻塞 0 ｜ 待办 3 ｜ 逾期 0
预估工时 144.0h，已完成 122.0h（84.7%）

| ID | 状态 | 标题 | 负责人 | 估时(h) | 截止 | 标签 |
| --- | --- | --- | --- | --- | --- | --- |
| T-001 | 完成 | M1：项目骨架与模型工具调用跑通 | lenovo | 10.0 | 2026-11-02 | m1 |
| T-002 | 完成 | M1：电商演示数据模型与初始化脚本 | lenovo | 8.0 | 2026-11-02 | m1 |
| T-003 | 完成 | M1：对话接口与消息持久化 | lenovo | 10.0 | 2026-11-04 | m1 |
| T-004 | 完成 | M2：表结构检索与 NL2SQL 生成 | lenovo | 12.0 | 2026-11-09 | m2 |
| T-005 | 完成 | M2：SQL 只读安全校验与执行确认 | lenovo | 12.0 | 2026-11-11 | m2 |
| T-006 | 完成 | M2：Redis 高频问答缓存与审计日志 | lenovo | 8.0 | 2026-11-13 | m2 |
| T-007 | 完成 | M3：文档上传、切分与向量化管道 | lenovo | 10.0 | 2026-11-18 | m3 |
| T-008 | 完成 | M3：RAG 检索、引用回答与拒答路由 | lenovo | 12.0 | 2026-11-20 | m3 |
| T-009 | 完成 | M3：多轮上下文压缩与对话摘要 | lenovo | 8.0 | 2026-11-22 | m3 |
| T-010 | 完成 | M4：50 条评估集与自动评估脚本 | lenovo | 12.0 | 2026-11-27 | m4 |
| T-011 | 完成 | M4：Prompt、chunk、TopK 对比实验 | lenovo | 8.0 | 2026-11-29 | m4 |
| T-012 | 完成 | M4：核心单元测试与异常场景测试 | lenovo | 12.0 | 2026-12-02 | m4 |
| T-013 | 待办 | M5：Docker Compose 部署与环境隔离 | lenovo | 8.0 | 2026-12-04 | m5 |
| T-014 | 待办 | M5：README、架构图与 API 文档 | lenovo | 8.0 | 2026-12-06 | m5 |
| T-015 | 待办 | M5：演示录屏与面试深挖手册 | lenovo | 6.0 | 2026-12-07 | m5 |

## 交付物清单

| 编号 | 类型 | 标题 | 路径 | 更新时间 |
| --- | --- | --- | --- | --- |
| REQ-001 | requirement | 智能问数 Agent 实习作品项目 | `docs/requirements/REQ-001-chatbi-agent.md` | 2026-10-24T03:50 |
| PLAN-001 | plan | 智能问数 Agent 六周交付计划 | `docs/plan/PLAN-001-six-week-mvp.md` | 2026-10-24T03:51 |

## 最近事件

| 时间 | 事件 | 说明 |
| --- | --- | --- |
| 2026-10-24 08:07:21 | `gate.run` | phase=develop, scope=exit, ok=True, errors=0, warnings=1 |
| 2026-10-24 08:07:21 | `task.update` | id=T-012, fields=status |
| 2026-10-24 08:03:44 | `task.update` | id=T-012, fields=status |
| 2026-10-24 07:14:01 | `gate.run` | phase=develop, scope=exit, ok=True, errors=0, warnings=1 |
| 2026-10-24 07:14:01 | `task.update` | id=T-011, fields=status |
| 2026-10-24 07:09:44 | `task.update` | id=T-011, fields=status |
| 2026-10-24 07:09:03 | `gate.run` | phase=develop, scope=exit, ok=True, errors=0, warnings=1 |
| 2026-10-24 07:09:03 | `task.update` | id=T-010, fields=status |
| 2026-10-24 07:02:08 | `task.update` | id=T-010, fields=status |
| 2026-10-24 07:00:49 | `gate.run` | phase=develop, scope=exit, ok=True, errors=0, warnings=1 |
