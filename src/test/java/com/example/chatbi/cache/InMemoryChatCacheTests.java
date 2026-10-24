package com.example.chatbi.cache;

import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

class InMemoryChatCacheTests {

    @Test
    void putThenGetReturnsValue() {
        InMemoryChatCache cache = new InMemoryChatCache();
        cache.put("k", "v", Duration.ofSeconds(60));

        assertThat(cache.get("k")).isEqualTo(Optional.of("v"));
        assertThat(cache.get("missing")).isEmpty();
    }

    @Test
    void expiredEntryIsMiss() throws InterruptedException {
        InMemoryChatCache cache = new InMemoryChatCache();
        cache.put("k", "v", Duration.ofMillis(50));

        Thread.sleep(150);

        assertThat(cache.get("k")).isEmpty();
    }

    @Test
    void overwritingKeyReplacesValue() {
        InMemoryChatCache cache = new InMemoryChatCache();
        cache.put("k", "old", Duration.ofSeconds(60));
        cache.put("k", "new", Duration.ofSeconds(60));

        assertThat(cache.get("k")).isEqualTo(Optional.of("new"));
    }
}
