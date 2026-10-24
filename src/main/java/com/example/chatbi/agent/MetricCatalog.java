package com.example.chatbi.agent;

import java.util.Map;

public final class MetricCatalog {
    private static final Map<String, String> METRICS = Map.of(
            "gmv", "SUM(orders.amount) where status is COMPLETED",
            "order_count", "COUNT(*) where status is COMPLETED",
            "refund_rate", "refund orders / total orders"
    );

    private MetricCatalog() {
    }

    public static boolean contains(String metric) {
        return METRICS.containsKey(metric.toLowerCase());
    }

    public static String definition(String metric) {
        return METRICS.getOrDefault(metric.toLowerCase(), "unknown metric");
    }
}
