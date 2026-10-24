# 智能问数 Agent(ChatBI Agent)

面向电商经营分析场景的智能问数系统:自然语言查数据(NL2SQL)、口径知识问答(RAG)、SQL 只读安全边界、可量化评估,一条 Docker Compose 命令起全栈。

## 核心能力

- **意图路由**:知识型问题(口径/定义/怎么算)进 RAG,指标问题走 NL2SQL,域外问题明确拒答——不编造内容
- **NL2SQL**:指标 × 区域 × 时间窗自然语言 → 只读聚合 SQL,附口径解释;`SqlGenerator` 接口化,可换 LLM 实现
- **SQL 安全边界**:单条 SELECT、表白名单、敏感字段(customer_phone)拦截、注释/多语句/标识符绕过封堵、禁 `SELECT *`;执行层 100 行 + 5 秒超时兜底;执行前需确认,服务端重新校验
- **RAG**:文档上传 → 段落切分(重叠保留)→ 向量化 → TopK 检索 → 引用式回答(文档/块号/得分);相似度低于阈值拒答
- **多用户隔离**:对话按用户隔离(非本人一律 404);审计日志记录每次 CHAT/SQL_CONFIRM(执行/缓存命中/拒绝及原因)
- **高频缓存**:Redis 缓存确认执行结果(`userId + sha256(sql)`,TTL 300s),**Redis 宕机自动降级**,主链路不受影响
- **多轮上下文压缩**:历史超阈值折叠为摘要 + 最近 N 条原文,提示词长度有界
- **可量化评估**:56 条评估集(四类)在线跑分 + 离线参数扫参实验,准确率可复现、可回归

## 快速开始

```bash
cp .env.example .env            # 按需改账号/端口
docker compose up -d --build    # MySQL 8.4 + Redis 7 + 应用,Flyway 自动迁移
curl http://localhost:8080/api/schema     # 验证
bash scripts/run-eval.sh                  # 56 条评估(当前 96.4%)
docker compose down                      # 停止,数据保留
```

本地开发(应用跑本机,基础设施进容器):

```bash
docker compose -f docker-compose.dev.yml up -d
./mvnw spring-boot:run    # 需 JDK 21
./mvnw test               # 103 个用例(H2,无需外部依赖)
```

## 一次问数怎么走

```
"北京近7天订单量" ──意图路由──▶ NL2SQL 生成只读 SQL ──▶ 展示给用户确认
                                                          │ 确认
"GMV 口径是什么"  ──意图路由──▶ RAG 检索 TopK ──▶ 引用式回答(文档#7 块0,得分0.83)
"食堂有什么菜"    ──意图路由──▶ 检索低于阈值 ──▶ 拒答(不编造)
              确认后:安全校验(服务端重验)→ 限流执行(100行/5s)→ 缓存 → 审计
```

完整链路时序图与数据模型见 [docs/architecture.md](docs/architecture.md);全部 18 个端点见 [docs/api.md](docs/api.md)。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 语言/框架 | Java 21、Spring Boot 3.5(Web/JDBC/Validation/Data-Redis) |
| 数据库 | MySQL 8.4 + Flyway 迁移(V1~V4,业务表/系统表/文档分块/评估集) |
| 缓存 | Redis 7(结果缓存,降级安全) |
| 测试 | JUnit 5 + MockMvc + H2(MySQL 模式),103 用例:单元 + API + 异常场景 + 评估门槛 |
| 部署 | Docker 多阶段构建,Compose 全栈一键,`.env` 环境隔离 |

## 质量与可观测

- **测试**:103 用例全绿;评估门槛固化进测试(NL2SQL ≥95%、RAG ≥90%、拒答 ≥90%、SQL 校验 ≥99%)
- **实验**:[RAG 参数扫参](docs/experiments/EXP-001-rag-sweep.md)——阈值主导召回/拒答权衡,线上配置是 96% 召回与 70% 拒答的工作点
- **审计**:`GET /api/audit`(仅 ADMIN)可追溯每次尝试
- 容器化部署验证抓出过两个 H2 测试看不见的 bug(缺 MySQL 驱动、KeyHolder 键名差异),均已修复并有测试覆盖

## 项目文档

- 需求与验收标准:[docs/requirements/REQ-001-chatbi-agent.md](docs/requirements/REQ-001-chatbi-agent.md)
- 六周交付计划:[docs/plan/PLAN-001-six-week-mvp.md](docs/plan/PLAN-001-six-week-mvp.md)
- 架构 / API / 实验:[docs/architecture.md](docs/architecture.md) · [docs/api.md](docs/api.md) · [docs/experiments/](docs/experiments/)
- 流程状态:`python tools/devflow/devflow.py status`
- 面试深挖手册:[docs/interview-guide.md](docs/interview-guide.md)

## 提交规范

分支:`feature/<需求号>-<简述>`、`fix/<需求号>-<简述>`、`release/vX.Y.Z`
提交:`<type>(<scope>): <简述>`,type ∈ feat / fix / docs / refactor / perf / test / build / ci / chore / revert

版本记录见 [CHANGELOG.md](CHANGELOG.md);流程状态存于 `.devflow/`(随代码提交)。
