# 演示脚本(录屏分镜)

> 任务:T-015(REQ-001)。目标时长 5~6 分钟。建议 OBS 录屏,1080p,鼠标跟随;口播词可直接照念。

## 录制前准备

```bash
cp .env.example .env
docker compose up -d --build        # 提前起好,录屏时已是健康状态
curl http://localhost:8080/api/schema   # 确认通
# 打开两个终端窗口:左边跑命令,右边随时切 docker compose logs -f chatbi-app(可选)
```

## 分镜

### 镜头 0|开场(30s)

> 口播:这是一个自然语言问数 Agent:能查电商经营数据、答口径问题、拒绝域外问题,SQL 有安全边界,全链路可审计可评估。整个系统一条 Docker Compose 命令起全栈。

```bash
docker compose ps        # 三个容器 healthy:app + MySQL + Redis
```

### 镜头 1|取数问题 → NL2SQL → 确认执行(90s)

> 口播:先看最核心的链路。用户在会话里问「北京近 7 天订单量」,系统识别这是取数问题,生成只读 SQL,但**不直接执行**——SQL 作为工具调用存档,等用户确认。

```bash
# 1. 建会话
curl -s -X POST localhost:8080/api/conversations -H "Content-Type: application/json" \
  -d '{"userId":1,"title":"经营分析"}'
# 取返回的 id 记为 $CONV,后续命令替换

# 2. 会话内提问 → 返回 execute_sql 工具调用
curl -s -X POST localhost:8080/api/conversations/$CONV/chat -H "Content-Type: application/json" \
  -d '{"userId":1,"question":"北京近7天订单量"}'
# 讲点:answer 是"已生成查询 SQL,确认后执行",toolCall.arguments.sql 是生成的只读聚合

# 3. 用户确认 → 服务端重新校验 → 限流执行
curl -s -X POST localhost:8080/api/sql/confirm -H "Content-Type: application/json" \
  -d '{"userId":1,"sql":"SELECT COUNT(*) AS order_count FROM orders o JOIN regions r ON r.id = o.region_id WHERE r.name = '"'"'北京'"'"' AND o.created_at >= TIMESTAMPADD(DAY, -7, CURRENT_TIMESTAMP)"}'
# 讲点:返回列+行+cacheHit:false

# 4. 再来一次 → cacheHit:true(Redis 生效)
# ↑ 直接重放上一条命令,强调 cacheHit 变了
```

### 镜头 2|知识问题 → RAG 引用回答 + 拒答(60s)

> 口播:问口径这种知识型问题,意图路由直接送进知识库检索,答案带引用。问完全无关的问题,系统明确拒答,不编造。

```bash
# 1. 传一篇口径文档
curl -s -X POST localhost:8080/api/documents -H "Content-Type: application/json" \
  -d '{"title":"业务口径说明","content":"GMV 的口径是已完成订单的金额总和。"}'

# 2. 知识问题 → RAG + 引用
curl -s -X POST localhost:8080/api/rag/query -H "Content-Type: application/json" \
  -d '{"question":"GMV 口径指的是什么"}'
# 讲点:route=RAG,citations 里有文档标题、块号、相似度得分

# 3. 域外问题 → 拒答
curl -s -X POST localhost:8080/api/rag/query -H "Content-Type: application/json" \
  -d '{"question":"食堂今天中午有什么菜"}'
# 讲点:route=REFUSED
```

### 镜头 3|安全边界(75s)——本项目的差异化亮点

> 口播:LLM 生成的 SQL 不能直接执行。校验器只放行单条 SELECT、白名单表,拒绝敏感字段、通配符、注释和多语句注入,执行层还有一百行和五秒超时兜底。每次尝试——包括被拒绝的——都写审计。

```bash
# 1. 正常查询放行(见镜头1的 confirm)
# 2. 删库语句 → 422
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8080/api/sql/confirm \
  -H "Content-Type: application/json" -d '{"userId":1,"sql":"DELETE FROM orders"}'

# 3. 堆叠注入 → 422
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8080/api/sql/confirm \
  -H "Content-Type: application/json" -d '{"userId":1,"sql":"SELECT 1; DROP TABLE orders"}'

# 4. 敏感字段(手机号)→ 422
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8080/api/sql/confirm \
  -H "Content-Type: application/json" -d '{"userId":1,"sql":"SELECT customer_phone FROM orders"}'

# 5. 查系统表 users → 422
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8080/api/sql/confirm \
  -H "Content-Type: application/json" -d '{"userId":1,"sql":"SELECT username FROM users"}'

# 6. 管理员看审计:以上每次尝试都有记录(含拒绝原因)
curl -s "localhost:8080/api/audit?userId=3&limit=6" | python -m json.tool
# 讲点:allowed=false 的行 reason 是"包含禁止的关键字: delete"等

# 7. 非管理员访问审计 → 403
curl -s -o /dev/null -w "%{http_code}\n" "localhost:8080/api/audit?userId=1"
```

### 镜头 4|多用户隔离(30s)

> 口播:多用户演示——北京分析师看不到上海分析师的会话,访问别人的对话返回 404 而不是 403,避免泄露对话存在性。

```bash
# 用 userId=2 访问 userId=1 刚才的会话
curl -s -o /dev/null -w "%{http_code}\n" "localhost:8080/api/conversations/$CONV/messages?userId=2"
# → 404
```

### 镜头 5|评估与实验(60s)

> 口播:整个系统的准确率是量化的:56 条评估集在线跑分,四类指标;检索参数不是拍脑袋,是 18 组扫参实验选出来的工作点。

```bash
bash scripts/run-eval.sh
# 讲点:总体 96%+;NL2SQL 100%、SQL 校验 100%、RAG 93%、拒答 90%

curl -s localhost:8080/api/experiments/rag-sweep | python -c "
import json,sys
r=json.load(sys.stdin)
print('best:', r['bestByRagHit']['config'], '| ragHit:', r['bestByRagHit']['ragHitRate'])"
```

### 镜头 6|收尾(30s)

> 口播:收个尾——103 个自动化测试覆盖单元、接口、异常场景和评估门槛;部署是多阶段 Docker 镜像加 Compose 全栈;代码、架构图、API 文档、实验报告、面试手册都在仓库里。谢谢观看。

```bash
docker compose ps
# 可选:展示 README / docs/architecture.md 的架构图
```

## 剪辑建议

- 每个镜头之间加 0.5s 黑场 + 章节标题(「取数链路」「安全边界」…)
- 422/403/404 的状态码用放大或高亮标注
- cacheHit:true 与 cacheHit:false 同屏对比最有说服力
- 全片不超过 6 分钟;细节问题留给面试深挖手册
