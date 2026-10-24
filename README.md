# 智能问数 Agent

> 由 devflow 初始化生成，请按实际项目补充。

## 项目简介

面向实习作品场景的智能问数 Agent：用户用自然语言查询电商经营数据，系统通过 NL2SQL 生成待确认 SQL，并结合 RAG 回答指标口径类问题，同时提供安全校验、拒答和可量化评估。

## 交付路线

- 需求与验收标准：`docs/requirements/REQ-001-chatbi-agent.md`
- 六周 WBS 与里程碑：`docs/plan/PLAN-001-six-week-mvp.md`
- 当前阶段与任务状态：`python tools/devflow/devflow.py status`

## 技术路线

- 后端：Java 21、Spring Boot 3.5(JdbcTemplate / Flyway / Validation)
- 存储：MySQL 8(业务与系统表)、Redis 7(高频问答缓存,宕机自动降级)
- 核心链路：意图路由 → NL2SQL / RAG 检索 → SQL 只读校验 → 执行确认 → 审计与评估
- 部署:Docker Compose 一键全栈

## 一键部署(Docker Compose)

```bash
cp .env.example .env          # 按需修改账号/端口
docker compose up -d --build  # 构建 app 镜像并启动 MySQL + Redis + 应用
# Flyway 启动时自动完成 V1~V4 迁移与种子数据
curl http://localhost:8080/api/schema            # 验证服务
bash scripts/run-eval.sh                          # 跑 56 条评估集
docker compose down                               # 停止(数据保留在卷里)
```

仅起基础设施做本地开发(应用在本机跑):

```bash
docker compose -f docker-compose.dev.yml up -d
./mvnw spring-boot:run
```

镜像为多阶段构建(Maven 构建 → JRE 运行,非 root 用户);MySQL/Redis 不对宿主机发布端口,应用走 compose 内部网络,环境差异通过 `.env` 隔离。

## 本地开发

```bash
# 查看当前流程阶段与全景状态
python tools/devflow/devflow.py status

# 校验当前阶段是否满足准出契约（CI 执行同一套命令）
python tools/devflow/devflow.py check
```

## 文档

完整交付物与流程见 [docs/README.md](docs/README.md)：

- 需求：`docs/requirements`
- 设计：`docs/design`、`docs/adr`
- 排期：`docs/plan`
- 评审：`docs/review`
- 测试：`docs/test`
- 发布：`docs/release`
- 复盘：`docs/retro`

## 提交规范

分支：`feature/<需求号>-<简述>`、`fix/<需求号>-<简述>`、`release/vX.Y.Z`
提交：`<type>(<scope>): <简述>`，type ∈ feat / fix / docs / refactor / perf / test / build / ci / chore / revert

## 发布

版本记录见 [CHANGELOG.md](CHANGELOG.md)。项目流程状态存放在 `.devflow/`（务必随代码提交）。
