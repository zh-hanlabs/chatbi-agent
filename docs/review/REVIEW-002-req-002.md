---
id: REVIEW-002
title: "REQ-002 权限与模型接入评审"
status: approved
owner: "lenovo"
reviewers: ["ZCode"]
created: 2026-10-24
updated: 2026-10-24
pr: "https://github.com/zh-hanlabs/chatbi-agent/pull/20"
branch: "feature/REQ-001-project-skeleton"
commits: ["f1bf2ed"]
comments_resolved: true
phase: review
---

# REVIEW-002 REQ-002 权限与模型接入评审

> 所属阶段：代码评审（review） ｜ 负责人：lenovo ｜ 意见闭环：true
> 收拢合入:PR #17/#18/#19/#20(stacked 链,提交历史完整)

## 1. 变更清单

| 文件/模块 | 变更类型 | 影响面 | 风险等级 |
| --- | --- | --- | --- |
| authz/(PermissionService + UserPermissions) | 新增 | 双执行点权限裁决 | P0 |
| api/(PermissionDeniedException/UserController/异常映射) | 新增 | 403 语义与权限视图接口 | P0 |
| nl2sql+rag+chat 接入权限 | 修改 | 生成层/confirm 层/chat 链路 | P0 |
| audit/AuditService | 修改 | record 改 REQUIRES_NEW(事务回滚不吞审计) | P0 |
| llm/(6 类:配置/客户端/LLM生成器/两个门面) | 新增 | OpenAI 兼容接入与回退 | P1 |
| eval/EvaluationService | 修改 | 评估以管理员身份路由 | P2 |
| .github/workflows/ci-tests.yml | 新增 | CI 测试+评估门槛 | P2 |
| 测试(+22 用例,总 125) | 新增/修改 | 权限 11 + LLM 门面 11 | P1 |

**对应需求/设计**:REQ-002 / DESIGN-001

**自查结果**

- [x] 本地跑通主流程与异常分支(权限 403/422、LLM 回退矩阵、审计断言)
- [x] 已补充单元测试(125 用例四层)
- [x] 无遗留调试代码与硬编码配置(Key/网关地址全部环境变量化)

## 2. 评审 checklist

**正确性**

- [x] 逻辑与 REQ-002 AC-1~AC-9 完全一致(逐条有测试)
- [x] 边界值处理正确(用户不存在=默认全拒;空 Key=回退;LLM 空响应/围栏输出/null metric)
- [x] 异常分支有明确的处理与返回(403/422/回退 warn 日志)
- [x] 幂等/并发安全:权限只读;Embedding 缓存 ConcurrentHashMap 上限 10k 防膨胀

**安全**

- [x] LLM 生成的 SQL 必须过 SqlSecurityValidator(与人工 SQL 同一标准)——红线
- [x] 越权:数据权限(区域/指标)双执行点;切换向量实现需重灌文档已注释说明
- [x] 无敏感信息进日志(LLM 提示词仅表结构与口径;回退日志只记原因)
- [x] 无明文密钥(api-key 环境变量,配置绑定默认空)

**性能**

- [x] 无 N+1(权限两条主键 JOIN;评估标题映射一次)
- [x] LLM 10s 超时硬上限;Embedding 同文本缓存
- [x] 无大对象常驻(缓存有上限清空策略)

**可维护性**

- [x] 门面模式隔离切换逻辑,调用方零改动
- [x] LlmProperties record 构造器绑定,默认值集中
- [x] 注释解释「为什么」(REQUIRES_NEW 的事务回滚语义、向量空间不兼容)

**可测性与可观测**

- [x] 22 个新用例(权限 11 + LLM 回退矩阵 11)
- [x] LLM 回退全部记 warn 日志;权限拒绝落审计
- [x] 开关已设计:chatbi.llm.api-key 空=全回退,一行环境变量切换

## 3. 评审意见

| # | 位置 | 意见 | 严重度 | 提出人 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 1 | ConversationService.chat | 权限异常导致事务回滚连审计一起回滚 | Major | ZCode(测试发现) | 已修复:record 加 REQUIRES_NEW |
| 2 | PermissionEnforcementApiTests | 知识路由用例依赖其他类先灌语料,CI 顺序不同即 flake | Major | CI 实跑发现 | 已修复:用例自灌语料+类内清库 |
| 3 | LlmProperties | record 缺 @ConfigurationProperties 注解,上下文启动失败 | Major | ZCode(编译后上下文测试) | 已修复 |
| 4 | PR 合并流程 | stacked PR 的 base 在合并时指向中间分支 | Minor | ZCode | 已处理:收拢 PR #20;教训记录 |

## 4. 遗留问题与跟进

- [x] 确认:所有评审意见已闭环

**已知边界(非缺陷)**:confirm 层只能校验区域字面量,指标无法从 SQL 可靠反推(DESIGN-001 风险表已明示);LLM 真机效果评估(EXP-002)待用户配 Key。
