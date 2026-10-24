package com.example.chatbi.cache;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.Optional;

/**
 * Redis 缓存实现。Redis 不可用时记警告并按未命中降级,保证问数主链路可用。
 */
@Component
@ConditionalOnProperty(name = "chatbi.cache.type", havingValue = "redis")
public class RedisChatCache implements ChatCache {

    private static final Logger log = LoggerFactory.getLogger(RedisChatCache.class);

    private final StringRedisTemplate redisTemplate;

    public RedisChatCache(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    @Override
    public Optional<String> get(String key) {
        try {
            return Optional.ofNullable(redisTemplate.opsForValue().get(key));
        } catch (RedisConnectionFailureException | IllegalStateException e) {
            log.warn("Redis 不可用,缓存按未命中降级: {}", e.getMessage());
            return Optional.empty();
        }
    }

    @Override
    public void put(String key, String value, Duration ttl) {
        try {
            redisTemplate.opsForValue().set(key, value, ttl);
        } catch (RedisConnectionFailureException | IllegalStateException e) {
            log.warn("Redis 不可用,跳过缓存写入: {}", e.getMessage());
        }
    }
}
