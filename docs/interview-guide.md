# 面试深挖手册

> 任务:T-015(REQ-001)。按「面试官顺着简历往下钻」的路径组织,每个问题的答案都对应仓库里的真实实现——能打开代码指给面试官看。配套演示流程见 [demo-script.md](demo-script.md)。

## 一、项目一句话与电梯陈述

**一句话**:自然语言问电商经营数据的 Agent:意图路由分流 NL2SQL 与 RAG,SQL 有只读安全边界和执行确认,全链路审计与缓存,56 条评估集量化准确率,Compose 一键部署。

**两分钟版**:用户提问后先做意图判别——问「GMV 口径是什么」这类知识问题进 RAG 引用式回答,问「北京近 7 天订单量」这类取数问题生成只读 SQL,交给用户确认后由服务端重新校验并限流执行;域外问题或检索相似度不足时明确拒答,不编造。每次尝试落审计,高频查询走 Redis 缓存且宕机自动降级。整个系统用 56 条评估集跑分回归,参数选择有扫参实验数据支撑。

## 二、必问的八个问题

### 1. 为什么 NL2SQL 用规则而不是直接上大模型?

三个理由(代码:`nl2sql/SqlGenerator.java` 接口 + `RuleBasedSqlGenerator` 实现):

- **演示域封闭**:指标只有 GMV/订单量/退款率 × 三个区域 × 时间窗,规则可以做到 100% 可解释、可测试、零幻觉——评估集上 26/26 全对。
- **接口先行**:`SqlGenerator` 是接口,调用方(RagRouter、ConversationService)只依赖抽象。接 LLM 时新增一个实现类,把 `BusinessSchemaService` 的表结构塞进提示词即可,其他层不动。
- **风险排序**:LLM 生成 SQL 的不可控性需要更强的校验器兜底;先把校验器、确认流、审计这些工程骨架在规则实现上打磨稳,换模型时只是换「生产 SQL 的方式」,安全边界复用。

**追问「那 LLM 方案你会怎么做」**:schema 检索(SELECT 列注释)→ 拼提示词(表结构 + 口径定义 + few-shot)→ 让模型输出 JSON(sql + explanation)→ 走同一条 `SqlSecurityValidator` + confirm 链路。校验器不信任任何生成方,这是分层防御。

### 2. SQL 只读校验具体挡什么?怎么挡的?

代码:`nl2sql/SqlSecurityValidator.java`,保守策略——无法确认安全即拒绝。检查顺序:空 → 多语句(分号)→ 注释(`--` `/*` `#`)→ 必须以 SELECT 开头 → 反引号/双引号标识符(MySQL 词法白名单绕过)→ 禁止词表(写动词 + `FOR UPDATE` + `INTO OUTFILE` + `benchmark/sleep` + `procedure`)→ 敏感列 `customer_phone` → 投影通配符 → 表白名单(FROM/JOIN 后的标识符必须在 orders/products/regions)。

**讲得出的细节**:
- 先剔除字符串字面量再扫关键字——`WHERE name = 'update; drop table'` 不误伤,也没法用字面量藏 payload(`SqlSecurityApiTests.stringLiteralsDoNotTriggerFalsePositives`)。
- 子查询的内层 FROM 同样过白名单:`SELECT t.a FROM (SELECT username FROM users) t` 拒绝。
- 算术 `*`(退款率 SQL 里的 `* 1.0`)与 `COUNT(*)` 不被通配符规则误伤。
- 测试驱动出的真实修复:`PROCEDURE analyse()` 注入向量最初是放行的,单元测试先红后绿把它加进禁止词(`SqlSecurityValidatorUnitTests`)。
- **执行层兜底**:校验通过也只给 100 行 + 5 秒超时(`SqlExecutionService`),校验被绕过时有第二层。

**追问「为什么不上 SQL 解析器(JSqlParser)」**:词法方案的误拒率可接受(演示域生成器产出的 SQL 全放行),且零依赖;AST 方案更严谨但引入解析器对 MySQL 方言的兼容成本。架构上校验器是独立类,替换实现不动调用方。

### 3. 意图路由怎么做的?为什么「GMV 口径是什么」不能直接进 NL2SQL?

代码:`rag/RagRouter.java`。规则:先匹配知识型意图关键词(口径/定义/是什么/怎么算…),命中 → 直接 RAG;未命中 → 尝试 NL2SQL 生成,成功返回 SQL,失败(无法识别指标)落到 RAG;RAG 最高分低于阈值 → 拒答。

「GMV 口径是什么」包含 "GMV",不先判意图会被当成取数问题——这是评估集建好后发现的(测试先失败),先意图后能力是修法。讲清顺序:**辨意图 → 算数 → 查文档 → 拒答**。

### 4. RAG 的检索是怎么实现的?为什么不用向量数据库?

代码:`rag/RetrievalService.java`。向量化是 `EmbeddingClient` 接口的确定性 Mock 实现:CJK 按 bigram 切分、拉丁按词,token 哈希投影到 128 维并 L2 归一化;检索是应用层全量余弦取 TopK。

- **为什么不用向量库**:演示语料是几十块,应用层扫描毫秒级;引入 pgvector/milvus 是为规模付费。接口已经隔离(`EmbeddingClient`/`RetrievalService`),换真实 Embedding + 向量库只改这两个类。
- **诚实说明局限**:哈希 bigram 向量分不清措辞变体(评估集 2 条 RAG 失败案例),真实 Embedding 预期解决——这正好引出「你知道自己方案的边界在哪」。
- **参数怎么选的**:[EXP-001](experiments/EXP-001-rag-sweep.md) 扫参 18 组:阈值 0.1→0.2→0.3,拒答准确率 0.10→0.70→1.00 而召回 0.93+→0.93→0.67;线上取 500/3/0.2 是 96% 召回与 70% 拒答的工作点。**有数据,不是拍脑袋**。

### 5. 缓存怎么设计的?Redis 挂了怎么办?

代码:`cache/ChatCache.java` 接口 + `RedisChatCache`/`InMemoryChatCache`(`@ConditionalOnProperty` 二选一)。键 = `userId + sha256(sql)`(用户隔离,见测试 `cacheIsScopedPerUser`);TTL 300s 可配。

**降级**:Redis 连接失败 catch 住,读按未命中、写跳过,只记 warn 日志——`RedisChatCacheDegradationTests` 指向本机死端口验证不抛异常。原则:**缓存是加速器不是依赖**。缓存命中也落审计(reason=cache_hit),演示时能直接看到第二次 confirm 返回 `cacheHit:true`。

### 6. 多轮上下文怎么控制长度?

代码:`chat/ContextCompressor.java`。历史 ≤ 10 条原样;超过后旧消息折成摘要(`Summarizer` 接口,规则实现:去重问题主线 ≤3 条 + 工具调用计数),保留最近 6 条原文。`GET /api/conversations/{id}/context` 可看压缩视图。换 LLM 摘要只是新增 `Summarizer` 实现。

### 7. 评估体系怎么建的?准确率怎么保证不悄悄退化?

- 56 条用例**入库**(V4 迁移),四类:NL2SQL 26(6 条精确 SQL 断言)、RAG 15、拒答 10、SQL 校验 5。
- `GET /api/evaluations` 在线跑真实链路;标准语料按专属标题幂等补齐,库里有用户文档也可复现(这里踩过坑:最初「非空即跳过」导致手动上传文档后评估环境漂移,已修)。
- **门槛固化进测试**:NL2SQL ≥95%、RAG ≥90%、拒答 ≥90%、校验 ≥99%——回归时退化了 CI 直接红。`scripts/run-eval.sh` 供 CI/演示用。

### 8. 测试策略?H2 和 MySQL 的差异坑?

103 用例分四层:纯 JUnit 单元(生成器/校验器/切分器/向量/压缩器)、SpringBootTest API(MockMvc + H2 MySQL 模式)、异常场景(400/404/415/422/405/504)、评估门槛。

**真实教训(面试亮点)**:容器化部署验证抓出两个 H2 全绿也发现不了的 bug——①pom 缺 `mysql-connector-j`(H2 掩盖了驱动缺失,MySQL 镜像启动即崩);②MySQL 驱动的 KeyHolder 返回 `GENERATED_KEY` 而 H2 返回 `id`,取自增主键逻辑按 `id` 过滤在 MySQL 上必炸。修法是 `db/KeyHolderUtil` 兼容两者。**结论**:「测试绿」不等于「能跑」,目标环境冒烟是必要的最后一道。

## 三、如果给我更多时间(展示规划能力)

1. 接真实 LLM:`SqlGenerator`/`Summarizer`/`EmbeddingClient` 三个接口位已留好,各加一个实现 + 配置开关,评估集重跑对比(EXP-002)
2. 权限下推到 SQL:现在 users 的区域/指标权限表已建好(V1),confirm 时校验 `userId` 的区域/指标权限与 SQL 涉及范围
3. 向量库替换 + pgvector,语料规模化后应用层扫描不可持续
4. SSE 流式输出与前端界面;WebSocket 多轮
5. CI 流水线:`run-eval.sh` + `mvnw test` 进 GitHub Actions,PR 门禁自动跑

## 四、容易被问倒的点(提前想好)

- **「规则式能叫 NL2SQL 吗?」**——回答:项目交付的是完整问数链路(路由/校验/确认/审计/评估),SQL 生产方式是该链路上的可替换组件;规则实现保证了链路本身的工程质量和可测性。
- **「并发怎么办?」**——诚实:单实例演示,HikariCP 连接池 + Redis 读写并发安全;多实例需要把内存缓存换 Redis(已是默认)并考虑缓存键一致性;评估/演示负载下无状态。
- **「为什么不用 Spring AI / LangChain4j?」**——演示域的核心复杂度在链路设计而非 SDK 集成;手写每一步(路由/校验/缓存/压缩)才能讲清楚原理;接口留好了,后续引入框架是增强不是重写。
