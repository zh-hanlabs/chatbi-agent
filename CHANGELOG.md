# Changelog

本文件遵循 Keep a Changelog 规范，语义化版本号。

## [v0.2.0] - 2026-10-24

权限执行与模型接入。

### 新增

- **数据权限执行**:区域/指标双执行点——生成层(nl2sql/rag/chat)越权 403,confirm 层 SQL 区域字面量越权 422;每次拒绝落审计(PERMISSION_DENIED);用户不存在默认全拒;知识型问题不受数据权限影响;`GET /api/users/{id}/permissions` 权限视图
- **LLM 接入(带回退)**:OpenAI 兼容客户端(RestClient,10s 超时,支持 GLM/DeepSeek/Qwen 网关);LLM 版 SqlGenerator(表结构+口径+few-shot 提示词,严格 JSON 契约,产出必须过只读安全校验器);Embedding 网关实现(同文本缓存);未配 Key 或任何失败自动回退规则/哈希实现,主链路可用性不降
- **CI**:`ci-tests.yml` 在 push/PR 上跑全量测试(含 56 条评估门槛断言)

### 修复

- chat 事务回滚连审计一起回滚(record 改 REQUIRES_NEW 独立事务)
- 知识路由测试用例顺序依赖(CI 环境暴露,改为自灌语料)
- LlmProperties record 缺 @ConfigurationProperties 致上下文启动失败

### 配置

- 新增 `chatbi.llm.*`(base-url/api-key/chat-model/embedding-model/timeout-seconds),api-key 为空即全部回退本地实现;环境变量 `CHATBI_LLM_*` 可覆盖

## [v0.1.0] - 2026-10-24

首个演示版:自然语言问数 Agent 全链路(REQ-001 / M1~M5)。

### 新增

- **多用户 Schema**(Flyway V1/V2):电商业务表(orders/products/regions)、用户与区域/指标权限、会话/消息/审计表,含演示种子数据
- **对话接口**:会话 CRUD、消息持久化、按用户隔离(非本人 404);多轮上下文压缩(阈值折叠摘要 + 保留近 N 条)
- **NL2SQL**:意图优先路由(口径/定义类知识问题直达 RAG);指标×区域×时间窗生成只读聚合 SQL,附口径解释;表结构检索接口
- **SQL 安全边界**:单条 SELECT、表白名单、敏感字段拦截、注释/多语句/标识符绕过封堵、禁 SELECT *;执行前确认流(服务端重验);执行层 100 行 + 5 秒超时兜底
- **缓存与审计**:Redis 结果缓存(userId+sha256 键,TTL 300s,宕机自动降级);全链路审计(执行/缓存命中/拒绝及原因),管理端查询仅 ADMIN
- **RAG 管道**:文档上传 → 段落切分(重叠 50 字)→ 128 维确定性向量 → TopK 检索 → 引用式回答/阈值拒答
- **评估与实验**:56 条评估集(四类)在线跑分 + 门槛固化进测试;RAG 参数扫参实验 18 组(EXP-001)
- **部署与文档**:多阶段 Dockerfile + Compose 全栈一键;README/架构图/API 文档/面试手册/演示脚本
- **测试**:103 用例四层覆盖(纯单元/API/异常场景/评估门槛),全绿

### 修复(过程发现并闭环)

- 补 mysql-connector-j(H2 测试掩盖的驱动缺失)
- KeyHolder 兼容 MySQL(GENERATED_KEY)与 H2(id)差异
- SqlSecurityValidator 拦截 `PROCEDURE analyse()` 注入向量
- 评估标准语料幂等化(专属标题检查)
- 知识型问题误路由 NL2SQL(意图优先)

## [Unreleased]

- 初始化 devflow 项目管控：需求说明书、六周 WBS、GitHub Actions 门禁与状态落盘。
- 搭建 Spring Boot 3 骨架，提供 Chat API、工具调用抽象和 Mock Agent，并补充接口测试。
