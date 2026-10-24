package com.example.chatbi.llm;

import com.example.chatbi.nl2sql.BusinessSchemaService;
import com.example.chatbi.nl2sql.GeneratedSql;
import com.example.chatbi.nl2sql.SqlGenerator;
import com.example.chatbi.nl2sql.SqlSecurityValidator;
import com.example.chatbi.nl2sql.TableSchema;
import com.example.chatbi.nl2sql.ValidationResult;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/**
 * LLM 版 SQL 生成:表结构 + 口径约束 + few-shot 喂给模型,要求输出 JSON;
 * 产出必须再过只读安全校验器——LLM 与人工构造的 SQL 同一标准。
 * 不支持的问题同样抛 UnsupportedQuestionException,由调用方按原语义处理。
 */
@Component
public class LlmSqlGenerator implements SqlGenerator {

    private static final String SYSTEM_PROMPT = """
            你是电商经营数据的取数助手。根据用户问题生成一条只读 MySQL 查询。

            规则:
            1. 只允许 SELECT 单条语句;只能使用下方给出的表。
            2. 指标口径:GMV = 已完成订单(COMPLETED)的 SUM(amount);订单量 = COUNT(*);退款率 = 退款订单数/总订单数。
            3. 区域过滤用 JOIN regions r ON r.id = o.region_id 加 r.name = '<区域名>'。
            4. 时间窗(如"近N天")用 o.created_at >= TIMESTAMPADD(DAY, -N, CURRENT_TIMESTAMP)。
            5. 只输出 JSON,不要多余文本:{"metric":"GMV|ORDER_COUNT|REFUND_RATE","sql":"...","explanation":"一句话口径解释"}
            6. 问题与电商经营指标无关时输出 {"metric":null}。""";

    private static final List<String> FEW_SHOTS = List.of(
            "问: 北京的 GMV\n答: {\"metric\":\"GMV\",\"sql\":\"SELECT SUM(o.amount) AS gmv FROM orders o JOIN regions r ON r.id = o.region_id WHERE o.status = 'COMPLETED' AND r.name = '北京'\",\"explanation\":\"统计北京区域已完成订单的金额总和\"}",
            "问: 近7天订单量\n答: {\"metric\":\"ORDER_COUNT\",\"sql\":\"SELECT COUNT(*) AS order_count FROM orders o WHERE o.created_at >= TIMESTAMPADD(DAY, -7, CURRENT_TIMESTAMP)\",\"explanation\":\"统计全部区域近7天订单总数\"}",
            "问: 上海的退款率\n答: {\"metric\":\"REFUND_RATE\",\"sql\":\"SELECT SUM(CASE WHEN o.status = 'REFUNDED' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS refund_rate FROM orders o JOIN regions r ON r.id = o.region_id WHERE r.name = '上海'\",\"explanation\":\"统计上海区域退款订单占比\"}");

    private final OpenAiCompatChatModel chatModel;
    private final BusinessSchemaService schemaService;
    private final SqlSecurityValidator validator;
    private final ObjectMapper objectMapper;

    public LlmSqlGenerator(OpenAiCompatChatModel chatModel, BusinessSchemaService schemaService,
            SqlSecurityValidator validator, ObjectMapper objectMapper) {
        this.chatModel = chatModel;
        this.schemaService = schemaService;
        this.validator = validator;
        this.objectMapper = objectMapper;
    }

    @Override
    public GeneratedSql generate(String question) {
        String userPrompt = buildUserPrompt(question);
        String content = chatModel.complete(SYSTEM_PROMPT, userPrompt);
        Parsed parsed = parse(content);
        if (parsed == null || parsed.metric() == null) {
            throw new com.example.chatbi.api.UnsupportedQuestionException(
                    "无法识别查询指标,请围绕 GMV / 订单量 / 退款率提问");
        }
        // LLM 产出的 SQL 与人工构造同一标准:必须过只读校验器
        ValidationResult verdict = validator.validate(parsed.sql());
        if (!verdict.allowed()) {
            throw new OpenAiCompatChatModel.LlmUnavailableException(
                    "LLM 生成的 SQL 未通过安全校验: " + verdict.reason());
        }
        return new GeneratedSql(parsed.sql(), parsed.metric(), extractTables(parsed.sql()), parsed.explanation());
    }

    private String buildUserPrompt(String question) {
        StringBuilder prompt = new StringBuilder("可用表结构:\n");
        for (TableSchema table : schemaService.businessTables()) {
            prompt.append("- ").append(table.tableName()).append("(")
                    .append(String.join(", ", table.columns().stream()
                            .map(column -> column.name() + " " + column.type()).toList()))
                    .append(")\n");
        }
        prompt.append("\n示例:\n");
        for (String shot : FEW_SHOTS) {
            prompt.append(shot).append("\n");
        }
        prompt.append("\n问: ").append(question);
        return prompt.toString();
    }

    private Parsed parse(String content) {
        try {
            // 容忍模型输出 ```json 围栏
            String json = content.trim();
            int fence = json.indexOf("```");
            if (fence >= 0) {
                int start = json.indexOf('{', fence);
                int end = json.lastIndexOf('}');
                if (start >= 0 && end > start) {
                    json = json.substring(start, end + 1);
                }
            }
            int start = json.indexOf('{');
            int end = json.lastIndexOf('}');
            if (start >= 0 && end > start) {
                json = json.substring(start, end + 1);
            }
            Map<?, ?> raw = objectMapper.readValue(json, Map.class);
            return new Parsed(
                    (String) raw.get("metric"),
                    (String) raw.get("sql"),
                    (String) raw.get("explanation"));
        } catch (Exception e) {
            return null;
        }
    }

    private List<String> extractTables(String sql) {
        String lower = sql.toLowerCase();
        return java.util.Arrays.stream(new String[]{"orders", "products", "regions"})
                .filter(lower::contains)
                .toList();
    }

    private record Parsed(String metric, String sql, String explanation) {
    }
}
