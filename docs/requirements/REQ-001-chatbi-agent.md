---
id: REQ-001
title: "智能问数 Agent 实习作品项目"
status: approved
priority: P1
owner: "lenovo"
source: "用户实习作品项目规划（面向 Java AI 方向 / Agent 工程实习岗）"
created: 2026-10-24
updated: 2026-10-24
reviewers: ["Codex"]
related: []
tags: [agent, chatbi, nl2sql, rag, java]
phase: intake
---

# REQ-001 智能问数 Agent 实习作品项目

> 所属阶段：需求立项（intake） ｜ 负责人：lenovo ｜ 状态：draft

## 1. 背景与问题

当前目标是做一个能投递 Java 后端、Java AI 方向和 Agent 工程实习岗位的作品项目。用户是大三学生，已有 Java 基础和 Agent 基础概念，但缺少一个同时覆盖工程能力、AI 应用能力和效果评估能力的完整作品。

从已调研 JD 看，“Spring Boot + MySQL + Redis + Function Calling + RAG + 智能问数 + 评估体系”在 Java AI 方向岗位中高度收敛。单纯聊天 Demo 或单纯 CRUD 系统均难以同时证明这两类能力，因此需要一个边界清晰、可部署、可量化评估的交叉项目。

## 2. 目标与非目标

**目标**（本期必须做到，可验收）

- 交付一个可本地运行的智能问数 Agent：支持自然语言查询业务数据、知识库问答和不确定场景拒答。
- 实现 NL2SQL 工具调用链路：包含表结构检索、SQL 生成、只读校验、执行前确认、结果总结。
- 实现 RAG 链路：支持文档上传、切分、向量化、检索和引用式回答。
- 建立不少于 50 条的评估集，输出 SQL 准确率、RAG 命中率、拒答准确率等指标报告。
- 使用 Docker Compose 一键启动，并提供 README、架构图、演示录屏和面试讲解文档。

**非目标**（本期明确不做，避免范围膨胀）

- 不追求通用自然语言数据库客户端，仅支持一个演示业务域（电商订单与商品分析）。
- 不微调模型，不做自研向量数据库，优先使用成熟模型 API 和嵌入式/服务端向量存储。
- 不做企业级权限体系完整实现，仅实现演示级角色与敏感字段拦截。
- 不追求高并发生产能力，重点验证正确性、安全边界和可评估性。

## 3. 用户故事

| 角色 | 场景 | 期望 | 优先级 |
| --- | --- | --- | --- |
| 业务用户 | 查询经营数据但不熟悉 SQL | 输入“上个月北京销量前 10 的商品是什么”，系统生成可确认 SQL 并返回结果和解读 | P0 |
| 业务用户 | 询问指标口径 | 输入“GMV 是否包含退款订单”，系统从知识库检索并带引用回答 | P0 |
| 面试官 | 快速判断项目真实性 | 查看架构图、评估指标、测试报告和录屏，确认项目不是简单 API 包装 | P0 |
| 系统管理员 | 防止误操作和越权 | 系统拦截非 SELECT、敏感字段、无时间范围的大表查询，并记录审计日志 | P0 |

## 4. 验收标准 (AC)

- [ ] AC-1：Given 数据库包含订单、商品、地区三张演示表，When 用户询问可明确映射的数据聚合问题，Then 系统展示生成 SQL，经确认后返回正确查询结果。
- [ ] AC-2：Given 用户提问“GMV 口径是否包含退款”，When 知识库存在对应文档片段，Then 回答包含业务口径和来源引用。
- [ ] AC-3：Given 用户要求删除、修改数据或查询敏感字段，When 请求进入 SQL 审核器，Then 系统拒绝执行并给出安全原因。
- [ ] AC-4：Given 模型无法确认指标、表字段或用户意图，When 置信度不足，Then 系统主动追问或拒答，不得编造结果。
- [ ] AC-5：Given 不少于 50 条评估用例，When 执行评估脚本，Then 输出 SQL 准确率、RAG 命中率、拒答准确率、平均响应时间和成本报告。
- [ ] AC-6：Given 全新机器已安装 Docker，When 执行 `docker compose up`，Then 项目可一键启动，README 可指引完成演示数据初始化和 API 调用。

## 5. 范围与依赖

**影响范围**

- 涉及模块：Chat API、Agent 路由、NL2SQL 工具、RAG 管道、SQL 安全校验器、对话记忆、评估脚本、管理端基础接口。
- 涉及接口/表：`POST /api/chat`、`POST /api/documents`、`POST /api/sql/confirm`、`GET /api/evaluations`；业务表包括 `orders`、`products`、`regions`，系统表包括 `conversations`、`messages`、`documents`、`audit_logs`、`evaluation_cases`。

**依赖**

| 依赖项 | 责任方 | 需要何时就绪 | 阻塞级别 |
| --- | --- | --- | --- |
| 大模型 API Key | 用户 | 开发第 1 天 | P0 |
| Docker Desktop / Engine | 用户 | 开发第 1 天 | P0 |
| MySQL 与 Redis 运行环境 | 用户 / Docker Compose | 第 1 周结束 | P0 |
| 向量存储选型验证 | 用户 | 第 2 周结束 | P1 |

## 6. 风险与对策

| 风险 | 可能性 | 影响 | 对策 | 负责人 |
| --- | --- | --- | --- | --- |
| 模型生成 SQL 错误或不安全 | 高 | 高 | 只读账号、SQL 白名单解析、敏感字段拦截、执行前确认、强制 LIMIT | lenovo |
| RAG 检索召回不稳定 | 中 | 高 | 建立评估集，对比不同 chunk 大小和检索 TopK，保留最佳配置 | lenovo |
| API 成本和限流影响开发 | 中 | 中 | 使用低价模型、缓存高频结果、失败用例离线重放 | lenovo |
| 项目范围膨胀 | 高 | 中 | 固定 6 周交付，进阶能力只保留评估体系、权限边界、多轮记忆三项 | lenovo |
| Spring AI / LangChain4j 版本变化 | 中 | 中 | 锁定版本，抽 model、embedding、vector store 接口适配层 | lenovo |

## 7. 优先级说明

- 业务价值：直接匹配 Java AI 方向和 Agent 工程实习 JD 的核心关键词，形成可展示、可量化、可深挖的个人作品。
- 紧急程度：高。大三实习投递窗口临近，项目需要在 6 周内完成第一版，后续再做增强。
- 分期策略：一期完成 NL2SQL、RAG、安全边界、评估体系和 Docker 部署；二期可扩展多租户权限、更多工具、性能压测和 Web 化报表。

## 8. 评审记录

| 时间 | 评审人 | 角色 | 结论 | 主要意见 |
| --- | --- | --- | --- | --- |
| 2026-10-24 | Codex | reviewer | 通过 | 范围聚焦实习作品，AC 可判定，风险与安全边界明确 |

**评审结论**：通过。后续如导师 / 同学提出岗位视角意见，在计划或实现中继续修正。

> 评审通过后执行：
> `devflow approve --target REQ-001 --by <姓名> --role reviewer`
> 并把头部 `status` 改为 `approved`，然后 `devflow phase enter --to plan`。
