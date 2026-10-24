---
id: RELEASE-001
title: "REQ-001 v0.1.0 首个演示版发布"
status: approved
owner: "lenovo"
version: "v0.1.0"
release_date: "2026-10-24"
window: "2026-10-24 单人演示项目,无生产流量,随时可发"
rollback_ready: true
env_ready: true
approver: "lenovo"
related: ["REQ-001", "REVIEW-001", "TEST-001"]
tags: ["mvp"]
phase: release
---

# RELEASE-001 REQ-001 v0.1.0 首个演示版发布

> 所属阶段：发布部署（release） ｜ 负责人：lenovo ｜ 版本：v0.1.0
> 单机演示发布:Docker Compose 全栈,无生产流量,回滚即回退镜像与数据卷。

## 1. 发布内容

| 项 | 内容 |
| --- | --- |
| 版本号 | v0.1.0 |
| 对应需求 | REQ-001(M1~M5 全部 15 任务) |
| 变更清单 | PR #16(收拢,含原 #2~#15 全部内容,commit 9efa73a) |
| 数据库变更 | Flyway V1~V4(建表+种子+评估集);迁移幂等,回滚=重建数据卷 |
| 配置变更 | 新增 chatbi.cache/rag/context 配置组;连接与端口全部 .env 化 |
| 依赖变更 | 新增 spring-boot-starter-data-redis、mysql-connector-j、flyway-mysql(runtime) |

## 2. 前置检查

- [x] 流水线最新一次运行为 success(mvnw clean test 103/103,BUILD SUCCESS)
- [x] P0/P1 缺陷已清零(REVIEW-001 六项全闭环;TEST-001 BUG 表全关闭)
- [x] 数据库变更已评审,脚本具备幂等与回滚能力(Flyway 版本化;down -v 重建)
- [x] 监控告警、日志、看板已就绪(演示级:应用日志 + 审计表 + healthcheck)
- [x] 回滚方案已确认并演练过(down/up 即完成,冒烟脚本验证)
- [x] 值班与联系方式已明确(单人项目,lenovo)

## 3. 发布步骤

| 步骤 | 操作 | 执行人 | 预期耗时 | 失败动作 |
| --- | --- | --- | --- | --- |
| 1 | `git tag v0.1.0 && git push --tags` | lenovo | 1min | 删除 tag 重打 |
| 2 | `docker compose down -v && docker compose up -d --build` | lenovo | 3~5min | 查 `docker compose logs app`,修复后重跑 |
| 3 | 冒烟:api/schema → chat → confirm → cacheHit → eval | lenovo | 2min | 任一失败:回到步骤 2 或回退上一个 tag |

**发布窗口**:随时(无生产流量;避开演示前一小时的镜像重建即可)。

## 4. 灰度与观测

| 阶段 | 流量比例 | 观察时长 | 关键指标 | 继续/回滚阈值 |
| --- | --- | --- | --- | --- |
| 全量(演示) | 100%(单人) | 5min | 三容器 healthy、冒烟通过、eval ≥95% | healthy 失败或 eval <95% → 重建/回退 |

**观测入口**:看板 `docker compose ps` ｜ 日志 `docker compose logs -f app` ｜ 审计 `GET /api/audit`

## 5. 回滚方案

**触发条件**:容器 unhealthy、冒烟任一步失败、评估 <95%。

**回滚步骤**

1. `docker compose down -v`(停栈清卷)
2. `git checkout <上一版本> && docker compose up -d --build`(v0.1.0 为首个版本,回退目标=重建同版本;后续版本回退上一 tag)
3. 数据库:Flyway 前滚式迁移,回滚以数据卷重建实现(演示数据可重灌,无生产数据)

**回滚后验证**:重跑冒烟四步(schema/chat/confirm/eval)。

**回滚演练结论**:2026-10-24 已演练(down -v 后全新卷重建,全链路通过)。

## 6. 发布后验证

| 验证项 | 方法 | 通过标准 | 执行人 | 结果 |
| --- | --- | --- | --- | --- |
| 核心链路冒烟 | demo-script.md 镜头 1 命令集 | 全部通过 | lenovo | 通过 |
| 监控无新增告警 | compose ps + logs 观察 | 无 | lenovo | 通过 |
| 数据一致性核对 | GMV=1098.00 与种子数据对账;eval 56 条 | 差异为 0 | lenovo | 通过 |

## 7. 发布记录

| 时间 | 阶段 | 操作人 | 结果 | 备注 |
| --- | --- | --- | --- | --- |
| 2026-10-24 | 全量 | lenovo | 成功 | 三容器 healthy,eval 96.4% |

**遗留问题**:哈希向量 2 条 RAG 用例(记录于 EXP-001,接真实 Embedding 后出 EXP-002);录屏待用户完成(demo-script.md)。
