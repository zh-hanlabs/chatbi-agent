# API 文档

> 任务:T-014(REQ-001)。Base URL:`http://localhost:8080`,所有请求/响应均为 JSON(`Content-Type: application/json`)。
> 演示用户(种子数据):`1`=北京分析师(仅北京,GMV/订单量)、`2`=上海分析师(仅上海,GMV/退款率)、`3`=管理员(全区域全指标)。

## 对话(conversations)

### POST /api/conversations — 创建对话

请求:`{ "userId": 1, "title": "北京经营分析" }`(userId 必填需存在,否则 404;title 非空,否则 400)

响应 201:

```json
{ "id": "6f1c...uuid", "userId": 1, "title": "北京经营分析", "createdAt": "...", "updatedAt": "..." }
```

### GET /api/conversations?userId=1 — 我的对话列表

按 `updated_at` 倒序,只返回该用户自己的对话。

### GET /api/conversations/{id}/messages?userId=1 — 对话消息

按时间正序。非本人对话返回 404(不泄露存在性)。

```json
[
  { "id": 11, "conversationId": "6f1c...", "role": "USER", "content": "北京近7天订单量", "toolCallJson": null, "createdAt": "..." },
  { "id": 12, "conversationId": "6f1c...", "role": "ASSISTANT", "content": "已生成查询 SQL,确认后执行: ...", "toolCallJson": "{\"id\":\"...\",\"name\":\"execute_sql\",\"arguments\":{\"sql\":\"...\"}}", "createdAt": "..." }
]
```

### POST /api/conversations/{id}/chat — 对话内提问

请求:`{ "userId": 1, "question": "北京近7天订单量" }`

链路:意图路由 → 知识型问题返回引用式回答;指标问题返回 `execute_sql` 工具调用(SQL 已落 `tool_call_json`,衔接 confirm);域外且检索分低于阈值 → 拒答文案。USER/ASSISTANT 消息自动落库并写 CHAT 审计。

响应 200:

```json
{ "answer": "...", "toolCall": { "id": "...", "name": "execute_sql", "arguments": { "sql": "SELECT ..." } }, "requiresTool": true, "userMessageId": 11, "assistantMessageId": 12 }
```

### GET /api/conversations/{id}/context?userId=1 — 压缩后的多轮上下文

历史 ≤ 10 条原样保留;超过后旧消息折叠为摘要,仅保留最近 6 条原文(阈值 `chatbi.context.*` 可配)。

```json
{ "summary": "此前对话共 3 次提问,主要问题: ...;其间生成过 3 次查询工具调用。", "keptMessages": [ ...最近6条... ], "droppedCount": 6, "totalMessages": 12, "compressed": true }
```

## NL2SQL

### GET /api/schema — 业务表结构

白名单表(orders/products/regions)的列结构,来自 information_schema;系统表不外泄。

### POST /api/nl2sql — 自然语言生成 SQL

请求:`{ "question": "北京上个月的 GMV 是多少" }`

响应 200:`{ "sql": "SELECT SUM(o.amount) AS gmv ...", "metric": "GMV", "tablesUsed": ["orders", "regions"], "explanation": "统计北京区域已完成订单的金额总和" }`

无法识别指标 → 422 `{"error":"无法识别查询指标,请围绕 GMV / 订单量 / 退款率提问"}`;空白问题 → 400。

## SQL 执行(确认流)

### POST /api/sql/validate — 预检(不执行)

请求:`{ "sql": "SELECT ..." }` → 200 `{ "allowed": true, "reason": null }`,拒绝时 reason 给出原因(多语句/注释/禁止关键字/敏感字段/通配符/表不在白名单)。

### POST /api/sql/confirm — 执行前确认

请求:`{ "userId": 1, "conversationId": "可选", "sql": "SELECT ..." }`

服务端重新校验(不信任客户端),通过后以 100 行上限、5 秒超时执行,结果按 `userId + sha256(sql)` 缓存 300 秒;**每次尝试(执行/缓存命中/拒绝)都写审计**。

响应 200:`{ "columns": ["gmv"], "rows": [{"gmv": 1098.00}], "rowCount": 1, "truncated": false, "cacheHit": false }`

拒绝 → 422(审计 allowed=false);SQL 语法/列错误 → 422;查询超时 → 504。

## 知识库与 RAG

### POST /api/documents — 上传文档(入库管道)

请求:`{ "title": "业务口径说明", "content": "GMV 的口径是...\n\n退款率按..." }`

段落切分(~500 字,超长段硬切 + 50 字重叠)→ 逐块向量化 → 落库,单事务。响应 201:`{ "documentId": 7, "title": "...", "chunkCount": 2 }`

### GET /api/documents / GET /api/documents/{id} / GET /api/documents/{id}/chunks

文档列表 / 详情(404 若不存在)/ 分块明细(含向量 JSON)。

### POST /api/rag/query — 完整路由问答

请求:`{ "question": "GMV 口径指的是什么" }`

响应 200:

```json
{ "route": "RAG", "answer": "GMV 的口径是已完成订单的金额总和。", "sql": null,
  "citations": [ { "documentId": 7, "documentTitle": "业务口径说明", "chunkIndex": 0, "content": "...", "score": 0.83 } ] }
```

`route` ∈ `NL2SQL`(返回 sql 字段)/ `RAG`(返回 citations)/ `REFUSED`(知识库无相关内容,不编造)。

### POST /api/rag/retrieve — 仅检索(调参/调试)

返回 TopK(`chatbi.rag.top-k`,默认 3)个命中块及得分。

## 审计与管理

### GET /api/audit?userId=3&limit=50 — 审计日志(仅 ADMIN)

非管理员 → 403。返回最近审计(倒序,上限 200):

```json
[ { "id": 21, "userId": 1, "conversationId": "6f1c...", "action": "SQL_CONFIRM", "question": "SELECT ...", "generatedSql": "SELECT ...", "allowed": false, "reason": "包含禁止的关键字: delete", "createdAt": "..." } ]
```

## 评估与实验

### GET /api/evaluations — 跑全量评估集

56 条用例(NL2SQL 26 / RAG 15 / 拒答 10 / SQL 安全校验 5),标准语料自动幂等补齐。响应:`{ "total": 56, "passed": 54, "accuracy": 0.964, "byCategory": {...}, "failures": [...] }`。命令行包装:`bash scripts/run-eval.sh`(有失败退出非零)。

### GET /api/experiments/rag-sweep — RAG 参数扫参

chunk{300,500,800} × TopK{1,3} × 阈值{0.1,0.2,0.3} 共 18 组配置的召回/拒答对比,含最优配置。结论见 [EXP-001](experiments/EXP-001-rag-sweep.md)。

## 兼容性说明

旧骨架端点保留:`POST /api/chat`(问答演示)、`GET /api/tools`(工具调用演示)。

## 错误码约定

| 状态码 | 场景 |
| --- | --- |
| 400 | 参数校验失败(空白/类型错)、JSON 解析失败 |
| 403 | 非管理员访问审计 |
| 404 | 资源不存在 / 非本人对话 / 用户不存在 |
| 405 | 方法不支持 |
| 415 | Content-Type 不是 JSON |
| 422 | 无法识别的问题 / SQL 被安全校验拒绝 / SQL 语法或列错误 |
| 504 | 查询超时(>5 秒) |
