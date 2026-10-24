package com.example.chatbi.db;

import org.springframework.jdbc.support.KeyHolder;

import java.util.Map;

/**
 * 从 KeyHolder 提取自增主键,兼容不同驱动的键名:
 * H2 返回 {id=.., created_at=..},MySQL Connector/J 返回 {GENERATED_KEY=..}。
 */
public final class KeyHolderUtil {

    private KeyHolderUtil() {
    }

    public static long extractId(KeyHolder keyHolder) {
        Map<String, Object> keys = keyHolder.getKeys();
        if (keys == null || keys.isEmpty()) {
            throw new IllegalStateException("未取到自增主键");
        }
        Object value = keys.entrySet().stream()
                .filter(entry -> entry.getKey().equalsIgnoreCase("id")
                        || entry.getKey().equalsIgnoreCase("GENERATED_KEY"))
                .map(Map.Entry::getValue)
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("未取到自增主键: " + keys.keySet()));
        return ((Number) value).longValue();
    }
}
