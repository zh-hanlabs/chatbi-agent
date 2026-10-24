package com.example.chatbi.cache;

import io.lettuce.core.ClientOptions;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

/**
 * Redis 不可用时的降级语义:读写都不得抛异常,读按未命中处理。
 * 指向本机必然未占用的端口,模拟 Redis 宕机。
 */
class RedisChatCacheDegradationTests {

    private static final int DEAD_PORT = 16379;

    private LettuceConnectionFactory connectionFactory;
    private RedisChatCache cache;

    @BeforeEach
    void setUp() {
        RedisStandaloneConfiguration standalone = new RedisStandaloneConfiguration("localhost", DEAD_PORT);
        LettuceClientConfiguration client = LettuceClientConfiguration.builder()
                .commandTimeout(Duration.ofMillis(300))
                .clientOptions(ClientOptions.builder()
                        .socketOptions(io.lettuce.core.SocketOptions.builder()
                                .connectTimeout(Duration.ofMillis(300))
                                .build())
                        .build())
                .build();
        connectionFactory = new LettuceConnectionFactory(standalone, client);
        connectionFactory.afterPropertiesSet();
        cache = new RedisChatCache(new StringRedisTemplate(connectionFactory));
    }

    @AfterEach
    void tearDown() {
        if (connectionFactory != null) {
            connectionFactory.destroy();
        }
    }

    @Test
    void getDegradesToMissWhenRedisDown() {
        assertThat(cache.get("any-key")).isEmpty();
    }

    @Test
    void putDoesNotThrowWhenRedisDown() {
        assertThatCode(() -> cache.put("any-key", "v", Duration.ofSeconds(60))).doesNotThrowAnyException();
    }
}
