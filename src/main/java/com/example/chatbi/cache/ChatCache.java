package com.example.chatbi.cache;

import java.time.Duration;
import java.util.Optional;

/**
 * 高频问答结果缓存抽象。实现必须自我兜底:缓存不可用时按未命中处理,不得影响主链路。
 */
public interface ChatCache {

    Optional<String> get(String key);

    void put(String key, String value, Duration ttl);
}
