---
id: DESIGN-001
title: "权限执行与模型接入设计"
status: approved
owner: "lenovo"
created: 2026-10-24
updated: 2026-10-24
related_requirement: ["REQ-002"]
reviewers: [ZCode]
tags: ["v0.2"]
phase: design
---

# DESIGN-001 权限执行与模型接入设计

> 所属阶段:方案设计(design)｜负责人:lenovo｜状态:draft
> 目标:不看代码即可实现本文档描述的两个能力:权限执行、LLM 接入(带回退)。

## 1. 总体方案

**一句话方案**:新增 `authz` 包做权限裁决(区域/指标两类),在「生成层(语义已知识)」与「confirm 层(区域字符串提取)」两个执行点强制;新增 `llm` 包做 OpenAI 兼容客户端,SqlGenerator/EmbeddingClient 提供 LLM 实现,未配 Key 或调用失败自动回退现有规则实现。

**关键链路**

```text
chat/nl2sql 请求(userId+question)
   → RagRouter 意图分流
   → [NL2SQL 分支] RuleBased/LLM SqlGenerator 产出(metric, region)
        → PermissionService.check(userId, metric, region)   ← 执行点1(语义完整)
        → 通过:返回 SQL / 拒绝:403 + 审计 PERMISSION_DENIED
   → [confirm 请求] SqlSecurityValidator 词法校验
        → PermissionService.checkRegions(userId, SQL 中出现的区域字面量) ← 执行点2
        → 通过:限流执行 / 拒绝:422 + 审计

LLM 调用链(任何一步失败 → 回退规则实现,记 warn):
   LlmSqlGenerator: BusinessSchemaService 表结构 + 口径提示词 + few-shot
        → ChatModelClient.complete(prompt) → 解析 JSON{sql,metric,explanation}
        → SqlSecurityValidator 预检(不通过也回退规则)
```

**关键选型**

| 关注点 | 选型 | 为什么是它 | 备选为何没选 |
| --- | --- | --- | --- |
| 权限数据来源 | 直查 user_region/metric_permissions 表 | 数据已存在(V1),量级 3 用户,无需缓存 | 内存缓存(过度设计) |
| confirm 层区域提取 | SQL 字符串中匹配封闭区域集合字面量 | 区域只有 北京/上海/广州,确定性提取 | SQL AST 解析(重依赖,收益低) |
| LLM 协议 | OpenAI 兼容 /chat/completions + /embeddings(可配 base-url) | 兼容 GLM/DeepSeek/Qwen 等主流网关,一套客户端通吃 | 各家私有 SDK(绑定供应商) |
| HTTP 客户端 | Spring 自带 RestClient | 零新依赖 | WebClient(响应式,用不上) |
| 回退策略 | 失败即回退规则实现,不重试 | 可用性优先(与缓存降级同一哲学);演示域规则实现已达 100% | 重试+熔断(复杂度不匹配量级) |

## 2. 详细设计

### 2.1 模块划分

- `authz/PermissionService`:loadUserPermissions(userId) → {regions, metrics};check(userId, metric, regionOrNull);checkRegionsInSql(userId, sql)。无该用户 → 视为无任何权限。
- `authz/PermissionDeniedException` → 全局 403。
- `llm/ChatModelClient`:complete(systemPrompt, userPrompt) → String;`llm/OpenAiCompatChatModel`(RestClient,config: base-url/api-key/model/timeout)。
- `llm/LlmSqlGenerator implements SqlGenerator`:拼提示词(表结构+口径+输出 JSON 约束+few-shot 3 例)→ 调用 → 解析 → 安全校验器预检;任一步失败抛内部回退信号。
- `llm/SqlGeneratorDelegate`(门面,@Component):有 Key 且 LLM 成功 → LLM 结果;否则 RuleBasedSqlGenerator。调用方(RagRouter/ConversationService/Nl2SqlController)零改动依赖门面。
- `llm/EmbeddingClientDelegate` 同构:有 Key → OpenAI /embeddings(缓存同文本向量,ConcurrentHashMap);失败/无 Key → MockEmbeddingClient。
- `api/UserController`:GET /api/users/{id}/permissions。

### 2.2 核心流程(权限执行)

1. 生成层:SqlGenerator 返回 GeneratedSql(metric, sql, tablesUsed, explanation)后,由 Nl2SqlController/RagRouter 统一调 PermissionService.check(userId, metric, region-from-question)。失败:403 + 审计(PERMISSION_DENIED, reason=无 XX 区域/指标权限);成功:继续原链路。
2. confirm 层:校验器通过后,提取 SQL 中 r.name = 'X' 或 name = 'X' 的 X∈区域集合;逐一 check;任一无权限 → 422(审计 reason 含越权区域)。
3. chat 对话链:NL2SQL 路由分支在返回 execute_sql 前同样执行生成层检查;RAG 分支不受权限影响(口径文档全员可读)。

### 2.3 一致性设计

- 幂等键:权限查询只读;审计插入天然幂等(自增)。
- 事务边界:权限拒绝不产生消息写入;确认执行事务同 v0.1.0。
- 并发控制:无锁(读多写少,演示量级);LLM 向量缓存 ConcurrentHashMap 只增不减(容量上限 10k 条后清空重建,防泄漏)。

## 3. 接口契约

### 3.1 HTTP

新增:

```http
GET /api/users/1/permissions
→ 200 {"userId":1,"regions":["北京"],"metrics":["GMV","ORDER_COUNT"]}
```

行为变更(错误语义增强):

| 接口 | 新错误 |
| --- | --- |
| POST /api/nl2sql、POST /api/rag/query、chat | 403 {"error":"无上海区域的查询权限"} / {"error":"无 REFUND_RATE 指标的查询权限"} |
| POST /api/sql/confirm | 422 {"error":"无上海区域的查询权限"}(区域越权) |

### 3.2 错误码

| 错误码 | HTTP 状态 | 含义 | 客户端建议 |
| --- | --- | --- | --- |
| PERMISSION_DENIED | 403 | 生成层区域/指标越权 | 提示用户可查范围 |
| SQL_NOT_ALLOWED(复用) | 422 | confirm 层区域越权 | 同上 |

## 4. 数据模型

**零新增表**。复用:users(role)、user_region_permissions(user_id, region_id→regions.name)、user_metric_permissions(user_id, metric)。权限 JOIN 查询走已有 PK,量级 3 用户 × ≤3 行,无需索引变更。

**兼容性**:老数据无需处理;权限为空的用户(新注册)默认拒绝全部指标问题、RAG 正常。

## 5. 容量与性能

| 指标 | 当前 | 方案上线后目标 | 测算依据 |
| --- | --- | --- | --- |
| 权限查询延迟 | - | <5ms(两条主键 JOIN) | 本地 MySQL 实测量级 |
| LLM 生成延迟 | 0(规则) | 无 Key 0;有 Key 1~5s | 网关典型 RT |
| 评估准确率 | 96.4% | ≥96.4%(回退保证不降) | 评估集回归 |

**瓶颈与对策**:LLM 延迟 → 超时 10s 硬上限后回退;向量缓存膨胀 → 容量上限清空。

## 6. 异常处理与降级

| 异常场景 | 系统行为 | 用户可见表现 | 是否告警 |
| --- | --- | --- | --- |
| LLM 超时/非 200/JSON 解析失败/校验器拒绝 | 立即回退规则实现(单次请求内) | 正常得到规则版结果 | warn 日志 |
| Embedding HTTP 失败 | 回退哈希向量 | 检索质量回落但仍可用 | warn 日志 |
| 权限表无该用户记录 | 视为无权限 | 指标问题 403 | - |

## 7. 安全与合规

- [x] 鉴权:生成层(userId 语义)与 confirm 层(SQL 字面量)双层权限模型明确
- [x] 越权:水平(跨用户对话 404)已有;数据权限(区域/指标)本期补齐;垂直(审计仅 ADMIN)已有
- [x] 敏感数据:LLM 提示词只含表结构与口径,不含任何用户数据行
- [x] 输入校验:LLM 输出必须过 SqlSecurityValidator 才可返回(与人工构造 SQL 同一标准)
- [x] 限流:LLM 客户端 10s 超时;confirm 100 行/5s 不变

## 8. 可观测性

| 观测维度 | 关键项 | 告警阈值 | 看板位置 |
| --- | --- | --- | --- |
| 日志 | LLM 回退原因(超时/解析/校验拒) | 回退率 >50% 人工关注 | docker logs |
| 审计 | PERMISSION_DENIED 记录 | - | GET /api/audit |
| 评估 | 每次 CI 的准确率 | <95% 阻断 | Actions/EvaluationApiTests |

## 9. 测试策略

- 单元:PermissionService(JOIN 与默认拒绝)、区域提取器(全组合)、LlmSqlGenerator 提示词拼接与 JSON 解析(桩客户端)、回退触发矩阵
- 集成(MockMvc/H2):AC-1~AC-5 全部用例;无 Key 回归(v0.1.0 全量用例不变绿)
- 评估:56 条门槛不降;LLM 实现的真机评估待 Key(记录进 EXP-002,不阻塞本期)
- 压测:非目标

## 10. 评审记录

| 时间 | 评审人 | 角色 | 结论 | 主要意见 |
| --- | --- | --- | --- | --- |
| 2026-10-24 | ZCode | reviewer | 通过 | 双执行点取舍清晰;LLM 输出过校验器是关键红线 |

**评审结论**:通过。
