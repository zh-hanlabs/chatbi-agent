package com.example.chatbi.cache;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 进程内缓存兜底:本地未部署 Redis 或测试环境使用。
 * 过期条目在读写时顺带清理,避免另起清扫线程。
 */
@Component
@ConditionalOnProperty(name = "chatbi.cache.type", havingValue = "memory", matchIfMissing = true)
public class InMemoryChatCache implements ChatCache {

    private record Entry(String value, long expiresAtMillis) {
    }

    private final Map<String, Entry> store = new ConcurrentHashMap<>();

    @Value("${chatbi.cache.ttl-seconds:300}")
    private long defaultTtlSeconds;

    @Override
    public Optional<String> get(String key) {
        Entry entry = store.get(key);
        if (entry == null) {
            return Optional.empty();
        }
        if (System.currentTimeMillis() >= entry.expiresAtMillis()) {
            store.remove(key);
            return Optional.empty();
        }
        return Optional.of(entry.value());
    }

    @Override
    public void put(String key, String value, Duration ttl) {
        Duration effective = ttl != null && !ttl.isZero() && !ttl.isNegative() ? ttl
                : Duration.ofSeconds(defaultTtlSeconds);
        store.put(key, new Entry(value, System.currentTimeMillis() + effective.toMillis()));
    }
}
