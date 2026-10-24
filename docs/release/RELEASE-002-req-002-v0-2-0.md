---
id: RELEASE-002
title: "REQ-002 v0.2.0 权限与模型接入发布"
status: approved
owner: "lenovo"
version: "v0.2.0"
release_date: "2026-10-24"
window: "单人演示项目,无生产流量,随时可发"
rollback_ready: true
env_ready: true
approver: "lenovo"
related: ["REQ-002", "DESIGN-001", "REVIEW-002", "TEST-002"]
tags: ["v0.2"]
phase: release
---

# RELEASE-002 REQ-002 v0.2.0 权限与模型接入发布

> 所属阶段：发布部署（release） ｜ 负责人：lenovo ｜ 版本：v0.2.0
> 回滚即回退 tag:重建 Docker 栈;无数据库结构变更。

## 1. 发布内容

| 项 | 内容 |
| --- | --- |
| 版本号 | v0.2.0 |
| 对应需求 | REQ-002(AC-1~AC-9) |
| 变更清单 | PR #17/#18/#19/#20(权限执行、LLM 接入回退、CI) |
| 数据库变更 | 无(复用 V1~V4) |
| 配置变更 | 新增 chatbi.llm.*(base-url/api-key/模型/超时),默认未启用 |
| 依赖变更 | 无新增依赖(RestClient 用 Spring 自带) |

## 2. 前置检查

- [x] 流水线最新一次 success(ci-tests 在 GitHub runner 实跑 125/125)
- [x] P0/P1 缺陷清零(REVIEW-002 意见全闭环)
- [x] 数据库变更:无
- [x] 可观测:LLM 回退 warn 日志、权限拒绝审计、CI 门槛
- [x] 回滚方案确认(回退 v0.1.0 tag 重建栈)
- [x] 值班:lenovo(单人)

## 3. 发布步骤

| 步骤 | 操作 | 执行人 | 预期耗时 | 失败动作 |
| --- | --- | --- | --- | --- |
| 1 | git tag v0.2.0 && git push --tags | lenovo | 1min | 重打 |
| 2 | docker compose down -v && up -d --build | lenovo | 5min | logs 排查,必要时回退 v0.1.0 |
| 3 | 冒烟:权限 403/422、GMV、eval | lenovo | 2min | 同上 |

## 4. 灰度与观测

| 阶段 | 流量比例 | 观察时长 | 关键指标 | 回滚阈值 |
| --- | --- | --- | --- | --- |
| 全量(演示) | 100% | 5min | 容器 healthy、权限语义正确、eval ≥95% | 任一失败回退 v0.1.0 |

## 5. 回滚方案

**触发**:冒烟失败/评估 <95%。
**步骤**:`docker compose down -v` → `git checkout v0.1.0` → `up -d --build` → 重跑冒烟。
**演练**:v0.1.0 发布时已演练同流程。

## 6. 发布后验证

| 验证项 | 方法 | 通过标准 | 结果 |
| --- | --- | --- | --- |
| 权限冒烟 | u1 问上海 GMV | 403 | 通过 |
| 无 Key 回归 | GMV confirm | 200+1098 | 通过 |
| 评估 | GET /api/evaluations | ≥95% | 通过 |

## 7. 发布记录

| 时间 | 阶段 | 操作人 | 结果 | 备注 |
| --- | --- | --- | --- | --- |
| 2026-10-24 | 全量 | lenovo | 成功 | 125 用例双环境绿 |

**遗留问题**:EXP-002(真机 LLM 效果评估)待用户配 Key;confirm 层指标反推边界(DESIGN-001 已声明)。
