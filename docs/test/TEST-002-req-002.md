---
id: TEST-002
title: "REQ-002 权限与模型接入测试计划"
status: approved
owner: "lenovo"
created: 2026-10-24
updated: 2026-10-24
env: "H2(本地+CI) / Docker Compose(冒烟)"
build: "f1bf2ed(PR #20 收拢合并)"
related_requirement: ["REQ-002"]
tags: ["v0.2"]
phase: test
---

# TEST-002 REQ-002 权限与模型接入测试计划

> 所属阶段：测试验证（test） ｜ 负责人：lenovo ｜ 环境：H2(本地+CI) / Docker Compose(冒烟)

## 1. 测试范围

**包含**:REQ-002 AC-1~AC-9(权限执行、LLM 接入回退、CI);v0.1.x 行为回归

**不包含**:真实网关效果评估(EXP-002 待 Key;回退矩阵已用桩全覆盖)、压测(非目标)

## 2. 测试环境

| 项 | 值 | 备注 |
| --- | --- | --- |
| 环境 | 本地 H2 125 用例 + GitHub Actions ubuntu runner(同命令) + Docker 栈冒烟 | 三环境同源 |
| 版本/构建号 | f1bf2ed | 与发布候选一致 |
| 数据源 | 种子权限:u1=北京/GMV+订单量,u2=上海/GMV+退款率,u3=全权限 | 权限矩阵天然 |
| 依赖 Mock | OpenAiCompatChatModel 全桩测(Mockito) | 盲区=真机质量,留 EXP-002 |

## 3. 功能用例

| 用例编号 | 场景 | 操作步骤 | 预期结果 | 优先级 | 结果 |
| --- | --- | --- | --- | --- | --- |
| TC-001 | AC-1 区域越权 | u1 问「上海的 GMV」 | 403+审计 PERMISSION_DENIED | P0 | 通过 |
| TC-002 | AC-2 指标越权 | u1 问「北京的退款率」 | 403+指明指标 | P0 | 通过 |
| TC-003 | AC-3 管理员全通过 | u3 问 4 类组合 | 全部正常生成 | P0 | 通过 |
| TC-004 | AC-4 confirm 越权 | u1 confirm 含上海 SQL | 422+审计 | P0 | 通过 |
| TC-005 | AC-5 权限视图 | GET /api/users/{id}/permissions | 权限集合/404 | P0 | 通过 |
| TC-006 | AC-6 无 Key 回归 | 空 api-key 全量 125 用例 | 与 v0.1.x 一致 | P0 | 通过 |
| TC-007 | AC-7 LLM 生成 | 桩返回合法 JSON | 采用 LLM 结果 | P1 | 通过 |
| TC-008 | AC-7 回退矩阵 | 超时/不可解析/SQL 未过校验/metric null | 回退规则/422 引导 | P1 | 通过 |
| TC-009 | AC-8 Embedding | 启用+失败/未启用/缓存命中计数 | 网关向量/回退/仅调一次 | P1 | 通过 |
| TC-010 | AC-9 CI | push+PR 触发 ci-tests | runner 上 125 绿(实跑验证) | P0 | 通过 |

## 4. 边界与异常用例

| 用例编号 | 场景 | 预期结果 | 优先级 | 结果 |
| --- | --- | --- | --- | --- |
| TC-101 | 不存在的用户问指标 | 默认全拒 403 | P0 | 通过 |
| TC-102 | chat 事务回滚不吞审计 | REQUIRES_NEW,审计留存 | P0 | 通过(修复后) |
| TC-103 | 测试顺序独立性 | CI 环境类序不同仍全绿 | P1 | 通过(修复后) |
| TC-104 | LLM 围栏/杂文本输出 | 解析或回退,不 500 | P1 | 通过 |

## 5. 性能与稳定性

| 用例编号 | 场景 | 预期结果 | 优先级 | 结果 |
| --- | --- | --- | --- | --- |
| TC-201 | LLM 超时 | 10s 硬上限后回退,主链路可用 | P1 | 通过(桩验证) |
| TC-202 | Embedding 缓存膨胀 | 10k 上限清空 | P2 | 通过(实现+注释) |

## 6. 回归策略

- 回归范围:全量 125 用例(`mvnw clean test`),本地与 CI 双环境
- 自动化:全部入 ci-tests.yml(push/PR 触发)
- 数据清理:H2 进程隔离;Docker 栈 down -v 重建

## 7. 出口准则

- [x] P0/P1 用例 100% 执行且全部通过
- [x] blocker/P0 缺陷清零(REVIEW-002 意见 1~3 全闭环)
- [x] 冒烟用例已入流水线(评估门槛断言)
- [x] 流水线最新一次 success(GitHub Actions 实跑 125 绿)

## 8. 执行结果

| 时间 | 执行人 | 构建号 | 执行范围 | 通过/总数 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-24 | ZCode | f1bf2ed | 全量(本地) | 125/125 | mvnw clean test |
| 2026-10-24 | ZCode | f96ece6 | 全量(CI) | 125/125 | GitHub Actions 实跑 |

**覆盖率**:四层用例说明见 v0.1.0 TEST-001;新增权限/LLM 22 用例均有断言。

## 9. 缺陷跟踪

| 缺陷编号 | 描述 | 严重级别 | 负责人 | 状态 |
| --- | --- | --- | --- | --- |
| BUG-007 | chat 事务回滚吞审计 | P0 | ZCode | 已关闭 |
| BUG-008 | 知识路由用例测试顺序依赖(CI flake) | P1 | ZCode | 已关闭 |
| BUG-009 | LlmProperties 缺注解致启动失败 | P1 | ZCode | 已关闭 |
| LIMIT-002 | confirm 层指标不可反推(设计边界,DESIGN-001 已声明) | P2 | lenovo | 已忽略(记录在案) |

> 通过:`devflow approve --target TEST-002 --by <测试负责人> --role qa`,再 `devflow phase enter --to release`。
