# 系统架构

> 任务:T-014(REQ-001)。本文给出总体架构、请求链路与数据模型三层视图,配合 [API 文档](api.md) 使用。

## 总体架构

```mermaid
flowchart TB
    subgraph Client["客户端 / 演示脚本"]
        UI["REST 调用方"]
    end

    subgraph App["chatbi-agent(Spring Boot 3.5, Java 21)"]
        direction TB
        API["API 层<br/>AgentController / ConversationController / SqlController<br/>DocumentController / RagController / EvaluationController"]
        ROUTER["RagRouter 意图路由<br/>知识型问题 → RAG;指标问题 → NL2SQL;其余 → 拒答"]
        NL2SQL["NL2SQL<br/>RuleBasedSqlGenerator(SqlGenerator 接口)<br/>BusinessSchemaService 表结构检索"]
        GUARD["SqlSecurityValidator 只读校验<br/>+ SqlExecutionService(100 行/5 秒兜底)"]
        RAG["RAG 管道<br/>TextChunker → EmbeddingClient → RetrievalService(TopK)<br/>→ RagAnswerService(引用/拒答)"]
        CHAT["对话域<br/>ConversationService + ContextCompressor(多轮压缩)"]
        AUDIT["AuditService 审计"]
        CACHE["ChatCache 抽象<br/>RedisChatCache(降级) / InMemoryChatCache"]
        EVAL["EvaluationService 评估"]
    end

    subgraph Storage["存储"]
        MYSQL[("MySQL 8.4<br/>业务表 + 系统表<br/>Flyway V1~V4")]
        REDIS[("Redis 7<br/>SQL 结果缓存 TTL 300s")]
    end

    UI --> API
    API --> ROUTER
    ROUTER -->|NL2SQL| NL2SQL
    ROUTER -->|RAG| RAG
    NL2SQL --> GUARD
    GUARD -->|执行| MYSQL
    GUARD --> CACHE
    CACHE <---> REDIS
    RAG --> MYSQL
    CHAT --> MYSQL
    AUDIT --> MYSQL
    EVAL --> ROUTER
    EVAL --> GUARD
```

## 一次问数的完整链路

```mermaid
sequenceDiagram
    participant U as 用户
    participant C as ConversationController
    participant R as RagRouter
    participant G as SqlGenerator
    participant V as SqlSecurityValidator
    participant E as SqlExecutionService
    participant DB as MySQL
    participant RC as Redis ChatCache

    U->>C: POST /api/conversations/{id}/chat(问题)
    C->>R: route(question)
    alt 知识型意图(口径/定义/怎么算)
        R-->>C: RAG 引用回答 / 拒答(阈值不足)
    else 指标问题
        R->>G: generate(question)
        G-->>R: 只读聚合 SQL + 口径解释
        R-->>C: execute_sql 工具调用(SQL 存 tool_call_json)
        Note over C: 落库 USER/ASSISTANT 消息,审计 route
    end
    U->>E: POST /api/sql/confirm(userId, sql)
    E->>RC: 命中?
    alt 缓存命中
        RC-->>E: 返回结果(cacheHit=true)
    else 未命中
        E->>V: 服务端重新校验(不信任客户端)
        alt 不通过
            V-->>E: 拒绝原因
            E-->>U: 422(审计 allowed=false)
        else 通过
            E->>DB: 执行(限 100 行/5 秒)
            E->>RC: 写缓存(TTL 300s)
            E-->>U: 列 + 行 + 截断标记(审计 executed)
        end
    end
```

## 数据模型(Flyway V1~V4)

```mermaid
erDiagram
    users ||--o{ user_region_permissions : "区域权限"
    users ||--o{ user_metric_permissions : "指标权限"
    users ||--o{ conversations : "创建"
    regions ||--o{ orders : "归属"
    products ||--o{ orders : "购买"
    conversations ||--o{ messages : "包含"
    users ||--o{ audit_logs : "操作"
    documents ||--o{ document_chunks : "切分(向量 JSON)"

    orders { bigint id PK
             varchar order_no UK
             bigint region_id FK
             bigint product_id FK
             decimal amount
             varchar status "CREATED/COMPLETED/REFUNDED" }
    users { bigint id PK
            varchar username UK
            varchar role "ANALYST/ADMIN" }
    conversations { varchar id PK "UUID"
                    bigint user_id FK
                    varchar title }
    messages { bigint id PK
               varchar conversation_id FK
               varchar role "USER/ASSISTANT/TOOL"
               text tool_call_json }
    audit_logs { bigint id PK
                 bigint user_id FK
                 varchar action "CHAT/SQL_CONFIRM"
                 boolean allowed
                 varchar reason "executed/cache_hit/拒绝原因" }
    documents { bigint id PK
                varchar title
                text content }
    document_chunks { bigint id PK
                      bigint document_id FK
                      int chunk_index
                      text embedding "128 维 JSON" }
```

## 关键设计决策

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| NL2SQL 实现 | 规则式 `SqlGenerator` + 接口抽象 | 演示域指标有限,规则可测可解释;接 LLM 只换实现 |
| 向量存储 | MySQL TEXT 列存 JSON,应用层余弦 | 演示级语料规模,避免引入向量库依赖;检索接口已隔离,可平滑换 pgvector |
| 安全边界 | 词法校验(白名单/黑名单/敏感列)+ 执行层兜底(限行/超时) | 双层防御;宁可误拒不可放过 |
| 缓存 | ChatCache 抽象,Redis 宕机降级为未命中 | 主链路可用性优先,缓存是加速器不是依赖 |
| 评估 | 评估集入库 + 在线接口 + 离线扫参 | 准确率可量化、可复现、可回归 |
| 多轮上下文 | 阈值触发压缩:摘要 + 最近 N 条原文 | 提示词长度有界,不丢近因上下文 |

更多取舍见 `docs/adr/` 与 [实验报告](experiments/EXP-001-rag-sweep.md)。
