---
id: REVIEW-001
title: "REQ-001 全量交付评审"
status: approved
owner: "lenovo"
reviewers: ["ZCode"]
created: "2026-10-24"
updated: "2026-10-24"
pr: "https://github.com/zh-hanlabs/chatbi-agent/pull/16"
branch: "feature/REQ-001-project-skeleton"
commits: ["9efa73a"]
comments_resolved: true
phase: review
---

# REVIEW-001 REQ-001 全量交付评审

> 所属阶段：代码评审（review） ｜ 负责人：lenovo ｜ 意见闭环：true
> 收拢合入:PR #16(M1~M5 全部 14 个任务,原 stacked 链 #2~#15 的内容完整保留)

## 1. 变更清单

| 文件/模块 | 变更类型 | 影响面 | 风险等级 |
| --- | --- | --- | --- |
| db/migration V1~V4(4 个 SQL) | 新增 | 表结构 + 种子数据 + 评估集,H2/MySQL 双兼容 | P1 |
| chat/(会话域 5 类) | 新增 | 对话 CRUD、消息持久化、上下文压缩 | P1 |
| nl2sql/(生成/校验/执行 7 类) | 新增 | 取数核心链路与安全边界 | P0 |
| rag/(管道/检索/路由 10 类) | 新增 | 知识库与引用回答 | P1 |
| cache/(2 实现 + 接口) | 新增 | Redis 缓存,宕机降级 | P1 |
| audit/ + 管理端接口 | 新增 | 全链路审计 | P1 |
| eval/(评估 + 扫参) | 新增 | 质量度量 | P2 |
| api/ 全部控制器与异常处理 | 新增/修改 | 18 个端点,6 类错误映射 | P1 |
| Dockerfile / docker-compose×2 | 新增 | 部署 | P2 |
| docs/(架构/API/实验/手册/脚本) | 新增 | 文档 | P3 |
| 测试(12 个测试类 103 用例) | 新增 | 四层覆盖 | P1 |

**对应需求/设计**:REQ-001;PLAN-001(T-002~T-015)

**自查结果**

- [x] 本地跑通主流程与异常分支(ExceptionScenarioApiTests 6 类错误码场景)
- [x] 已补充单元测试(103 用例:单元 30+/API/异常/评估门槛)
- [x] 无遗留调试代码与硬编码配置(账号端口全部 .env/环境变量化)

## 2. 评审 checklist

**正确性**

- [x] 逻辑与需求 AC 完全一致(56 条评估集对齐 AC,96.4% 达标)
- [x] 边界值处理正确(空文本/空历史/空知识库/阈值边界均有用例)
- [x] 异常分支有明确的处理与返回(400/403/404/405/415/422/504 全覆盖测试)
- [x] 幂等 / 并发安全:评估语料幂等补齐(专属标题检查);缓存键含 userId 隔离;写路径事务化。N/A 并发压测(演示定位,非目标)

**安全**

- [x] 无 SQL 注入:词法校验(多语句/注释/标识符绕过/禁止词/敏感列/表白名单)+ 执行层 100 行 5 秒兜底;字面量先剔除防误伤防藏毒;12 个攻击样本用例全拒
- [x] 无越权:对话按用户隔离(非本人 404 不泄露存在性);审计仅 ADMIN(403)
- [x] 无敏感信息进日志:customer_phone 被校验器拦截,不出现在任何日志
- [x] 无明文密钥:连接串账号走环境变量,.env.example 仅含本地演示默认值

**性能**

- [x] 无 N+1 查询、无循环内远程调用(检索标题一次建映射;缓存读写单次)
- [x] 慢 SQL 已有索引支撑(orders 区域/状态+时间复合索引,V1)
- [x] 无大对象常驻内存 / 无连接未关闭(JdbcTemplate 由容器管理;内存缓存惰性过期)

**可维护性**

- [x] 命名准确,无魔法值(阈值/TopK/行数/超时全部配置化)
- [x] 单方法复杂度可控,无明显重复(KeyHolderUtil 抽公共)
- [x] 注释解释「为什么」而非「是什么」(如「非本人对话一律 404 避免泄露存在性」)

**可测性与可观测**

- [x] 新增逻辑有单测覆盖(四层:纯 JUnit/MockMvc/异常/评估门槛)
- [x] 关键路径有日志与监控埋点(Redis 降级 warn;全链路审计落库)
- [x] 开关/灰度策略已设计(chatbi.cache.type 双实现切换;SqlGenerator/Summarizer/EmbeddingClient 三接口预留 LLM 替换位)

## 3. 评审意见

| # | 位置 | 意见 | 严重度 | 提出人 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 1 | SqlSecurityValidator | `PROCEDURE analyse()` 注入向量未拦截 | Major | ZCode(单测驱动) | 已修复:禁止词表加 procedure |
| 2 | pom.xml | 缺 mysql-connector-j,H2 掩盖驱动缺失 | Major | ZCode(容器验证) | 已修复:runtime 依赖 |
| 3 | ConversationRepository/DocumentRepository | MySQL KeyHolder 返回 GENERATED_KEY 与 H2 的 id 不一致 | Major | ZCode(容器验证) | 已修复:KeyHolderUtil 兼容两者 |
| 4 | EvaluationService.ensureCorpus | 「非空即跳过」导致库内有用户文档时评估环境漂移 | Minor | ZCode(容器验证) | 已修复:专属标题幂等检查 |
| 5 | RuleBasedSqlGenerator | 「GMV 口径」类知识问题被误路由到 NL2SQL | Major | ZCode(评估集发现) | 已修复:意图优先路由 |
| 6 | RetrievalService | 逐 chunk 查文档标题 N+1 | Minor | ZCode | 已修复:一次建映射 |

## 4. 遗留问题与跟进

- [x] 确认:所有评审意见已闭环(接受并有处理结论)

**已知局限(非缺陷,二期处理)**:哈希 bigram 向量对措辞变体区分度有限(评估集 2 条 RAG 用例失败,EXP-001 已量化);真实 LLM/Embedding 未接入(三接口位已留,接入后重跑评估与扫参出 EXP-002)。
