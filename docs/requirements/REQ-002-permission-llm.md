---
id: REQ-002
title: "权限执行与模型接入(二期)"
status: approved
priority: P1
owner: "lenovo"
source: "REQ-001 遗留缺口与二期路线(docs/interview-guide.md 第三节)"
created: 2026-10-24
updated: 2026-10-24
reviewers: [ZCode]
related: ["REQ-001"]
tags: ["v0.2"]
phase: intake
---

# REQ-002 权限执行与模型接入(二期)

> 所属阶段：需求立项（intake） ｜ 负责人：lenovo ｜ 状态：draft

## 1. 背景与问题

v0.1.0 交付了完整问数链路,但存在两个已知缺口:

1. **权限表建而未用**:V1 迁移创建了 `user_region_permissions`/`user_metric_permissions`(种子数据里北京分析师只有北京+GMV/订单量),但取数链路从未校验——北京分析师现在可以查上海退款率,多用户安全故事只做了一半(对话隔离有了,数据权限没有)。
2. **模型接入缺位**:SqlGenerator/EmbeddingClient/Summarizer 三个接口位留好了,但只有确定性 Mock/规则实现;评估集 2 条 RAG 用例(96.4% 中的 3.6% 缺口)的根因就是哈希向量对措辞变体的区分度。

## 2. 目标与非目标

**目标**（本期必须做到，可验收）

- 用户权限在取数链路强制生效:无权限的区域/指标问题被明确拒绝并落审计,权限内行为与 v0.1.0 一致
- 提供 OpenAI 兼容的 Chat/Embedding HTTP 客户端与 LLM 版 SqlGenerator/EmbeddingClient 实现;未配置 API Key 时自动回退现有规则实现,主链路可用性不降级
- GitHub Actions CI:PR 与 push 自动跑全量测试与评估门禁

**非目标**（本期明确不做，避免范围膨胀）

- 不做前端界面与 SSE 流式输出
- 不替换向量存储(仍为 MySQL JSON + 应用层余弦)
- 不做多租户/组织级权限体系(仍是演示级角色)
- 不做真实模型的调优实验(EXP-002 待 Key 配好后单独出)

## 3. 用户故事

| 角色 | 场景 | 期望 | 优先级 |
| --- | --- | --- | --- |
| 北京分析师 | 问「上海的 GMV」 | 明确告知无上海区域权限,不生成 SQL | P0 |
| 北京分析师 | 问「北京的退款率」 | 明确告知无退款率指标权限 | P0 |
| 管理员 | 问任意区域任意指标 | 正常走完整链路 | P0 |
| 管理理员 | 直接 confirm 一条含上海的 SQL | 服务端校验出区域越权并拒绝 | P0 |
| 开发者 | 配置 OpenAI 兼容 Key 后 | NL2SQL/Embedding 自动切 LLM 实现,不配则回退规则 | P1 |
| 维护者 | 提 PR | CI 自动跑 103+ 测试与评估门槛,退化即红 | P1 |

## 4. 验收标准 (AC)

- [ ] AC-1:Given 北京分析师(userId=1,区域=北京,指标=GMV/订单量) When chat/rag 问「上海的 GMV」 Then 403 且 reason 指明无上海区域权限,审计落 PERMISSION_DENIED
- [ ] AC-2:Given 同上用户 When 问「北京的退款率」 Then 403 指明无退款率指标权限
- [ ] AC-3:Given 管理员(userId=3,全权限) When 问任意组合 Then 与 v0.1.0 行为一致(评估不回退)
- [ ] AC-4:Given 任意用户 When confirm 的 SQL 含其无权限的区域(r.name='上海') Then 422 拒绝并审计
- [ ] AC-5:GET /api/users/{id}/permissions 返回该用户区域/指标权限集合
- [ ] AC-6:未配置 CHATBI_LLM_API_KEY 时 全部接口行为与 v0.1.0 回归一致(全量测试绿)
- [ ] AC-7:配置 Key 后 SqlGenerator 切换为 LLM 实现(带 schema 提示词与 JSON 输出约束),失败自动回退规则实现
- [ ] AC-8:配置 Key 后 EmbeddingClient 切换 HTTP 实现,失败回退哈希实现
- [ ] AC-9:GitHub Actions 在 push/PR 上执行 mvnw test 且评估门槛断言通过

## 5. 范围与依赖

**影响范围**

- 涉及模块:RagRouter/Nl2SqlController/SqlExecutionService(权限执行点)、chat 与 rag 新增 LLM 实现、CI 配置
- 涉及接口/表:`POST /api/nl2sql|/api/rag/query|/api/sql/confirm` 增加权限语义;`GET /api/users/{id}/permissions` 新增;复用 user_region_permissions/user_metric_permissions 表,无新表

**依赖**

| 依赖项 | 责任方 | 需要何时就绪 | 阻塞级别 |
| --- | --- | --- | --- |
| OpenAI 兼容 API Key(可选) | 用户 | T-003 开发时 | P1(无 Key 走回退,不阻塞) |
| GitHub Actions 可用 | 平台 | T-004 开发时 | P2 |

## 6. 风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| LLM 输出不稳定导致 SQL 校验拒绝率升高 | 取数成功率下降 | LLM 失败/解析失败自动回退规则实现;评估集对比两种实现的准确率 |
| 权限校验误伤(区域名误提取) | 合法查询被拒 | 区域为封闭集合(3 个),提取规则确定性;用例覆盖全组合 |
| 权限语义在 confirm 层不可完全推导(指标无法从 SQL 可靠反推) | 越权面收窄 | 生成层做完整语义校验,confirm 层做区域字符串校验并在文档中明示边界 |

## 7. 优先级说明

- **P0 权限执行(T-001)**:安全缺口,不做等于多用户故事只完成一半;且零外部依赖,先行
- **P1 LLM 接入(T-002/T-003)**:核心价值升级,回退机制保证无 Key 也可交付
- **P1 CI(T-004)**:小成本高保障,守住前两项成果

## 8. 评审记录

| 时间 | 评审人 | 角色 | 结论 | 主要意见 |
| --- | --- | --- | --- | --- |
| 2026-10-24 | ZCode | reviewer | 通过 | 权限为 P0 缺口应先做;LLM 回退设计保证可用性 |
