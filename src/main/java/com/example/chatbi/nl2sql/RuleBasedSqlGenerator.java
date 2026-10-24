package com.example.chatbi.nl2sql;

import com.example.chatbi.api.UnsupportedQuestionException;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 演示域的 NL2SQL 生成器：按「指标 + 区域 + 时间窗」三元组解析自然语言并拼装只读查询。
 * 后续接入真实大模型时，以 SqlGenerator 接口的 LLM 实现替换本规则实现。
 */
@Service
public class RuleBasedSqlGenerator implements SqlGenerator {

    private enum Metric {
        GMV("GMV", "SUM(o.amount) AS gmv", "已完成订单的金额总和", List.of("o.status = 'COMPLETED'")),
        ORDER_COUNT("ORDER_COUNT", "COUNT(*) AS order_count", "订单总数", List.of()),
        REFUND_RATE("REFUND_RATE",
                "SUM(CASE WHEN o.status = 'REFUNDED' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS refund_rate",
                "退款订单占比", List.of());

        final String name;
        final String projection;
        final String label;
        final List<String> filters;

        Metric(String name, String projection, String label, List<String> filters) {
            this.name = name;
            this.projection = projection;
            this.label = label;
            this.filters = filters;
        }
    }

    private static final List<String> REGIONS = List.of("北京", "上海", "广州");
    private static final Pattern RECENT_DAYS = Pattern.compile("(?:近|最近)(\\d+)(?:天|日)");

    @Override
    public GeneratedSql generate(String question) {
        Metric metric = detectMetric(question)
                .orElseThrow(() -> new UnsupportedQuestionException("无法识别查询指标，请围绕 GMV / 订单量 / 退款率提问"));
        Optional<String> region = REGIONS.stream().filter(question::contains).findFirst();
        Optional<Integer> recentDays = parseRecentDays(question);

        List<String> tables = new ArrayList<>(List.of("orders"));
        List<String> conditions = new ArrayList<>(metric.filters);
        if (region.isPresent()) {
            tables.add("regions");
            conditions.add("r.name = '" + region.get() + "'");
        }
        // TIMESTAMPADD 在 MySQL 与 H2(MySQL 模式)下均合法
        recentDays.ifPresent(days -> conditions.add(
                "o.created_at >= TIMESTAMPADD(DAY, -" + days + ", CURRENT_TIMESTAMP)"));

        StringBuilder sql = new StringBuilder("SELECT ").append(metric.projection)
                .append(" FROM orders o");
        if (region.isPresent()) {
            sql.append(" JOIN regions r ON r.id = o.region_id");
        }
        if (!conditions.isEmpty()) {
            sql.append(" WHERE ").append(String.join(" AND ", conditions));
        }

        return new GeneratedSql(sql.toString(), metric.name, tables, explain(metric, region.orElse(null)));
    }

    private Optional<Metric> detectMetric(String question) {
        String q = question.toLowerCase();
        if (q.contains("退款率") || q.contains("退款")) {
            return Optional.of(Metric.REFUND_RATE);
        }
        if (q.contains("gmv") || q.contains("成交") || q.contains("销售额") || q.contains("金额")) {
            return Optional.of(Metric.GMV);
        }
        if (q.contains("订单量") || q.contains("订单数") || q.contains("多少单") || q.contains("订单")) {
            return Optional.of(Metric.ORDER_COUNT);
        }
        return Optional.empty();
    }

    private Optional<Integer> parseRecentDays(String question) {
        Matcher matcher = RECENT_DAYS.matcher(question);
        if (matcher.find()) {
            return Optional.of(Integer.parseInt(matcher.group(1)));
        }
        return Optional.empty();
    }

    private String explain(Metric metric, String region) {
        StringBuilder explanation = new StringBuilder("统计");
        if (region != null) {
            explanation.append(region).append("区域");
        } else {
            explanation.append("全部区域");
        }
        explanation.append(metric.label);
        return explanation.toString();
    }
}
