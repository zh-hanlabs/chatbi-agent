package com.example.chatbi.chat;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class ContextCompressorUnitTests {

    private final ContextCompressor compressor = new ContextCompressor(new RuleBasedSummarizer(), 10, 6);

    private ChatMessage user(String content) {
        return new ChatMessage(1L, "c", "USER", content, null, null);
    }

    private ChatMessage assistant(String content) {
        return new ChatMessage(2L, "c", "ASSISTANT", content, null, null);
    }

    @Test
    void belowThresholdStaysVerbatim() {
        List<ChatMessage> messages = new ArrayList<>();
        for (int i = 0; i < 5; i++) {
            messages.add(user("问题" + i));
            messages.add(assistant("回答" + i));
        }

        ContextCompressor.CompressedContext context = compressor.compress(messages);

        assertThat(context.compressed()).isFalse();
        assertThat(context.droppedCount()).isZero();
        assertThat(context.keptMessages()).hasSize(10);
        assertThat(context.summary()).isNull();
    }

    @Test
    void atExactThresholdStillVerbatim() {
        List<ChatMessage> messages = new ArrayList<>();
        for (int i = 0; i < 5; i++) {
            messages.add(user("问题" + i));
            messages.add(assistant("回答" + i));
        }

        assertThat(compressor.compress(messages).compressed()).isFalse();
    }

    @Test
    void aboveThresholdKeepsRecentAndSummarizesRest() {
        List<ChatMessage> messages = new ArrayList<>();
        for (int i = 0; i < 6; i++) {
            messages.add(user("问题" + i));
            messages.add(assistant("回答" + i));
        }

        ContextCompressor.CompressedContext context = compressor.compress(messages);

        assertThat(context.compressed()).isTrue();
        assertThat(context.totalMessages()).isEqualTo(12);
        assertThat(context.droppedCount()).isEqualTo(6);
        assertThat(context.keptMessages()).hasSize(6);
        assertThat(context.keptMessages().getFirst().content()).isEqualTo("问题3");
        assertThat(context.summary()).contains("问题0").contains("问题1").contains("问题2");
    }

    @Test
    void customThresholdAndKeepRecent() {
        ContextCompressor custom = new ContextCompressor(new RuleBasedSummarizer(), 5, 2);
        List<ChatMessage> messages = List.of(
                user("a1"), assistant("r1"), user("a2"), assistant("r2"), user("a3"), assistant("r3"));

        ContextCompressor.CompressedContext context = custom.compress(messages);

        assertThat(context.compressed()).isTrue();
        assertThat(context.droppedCount()).isEqualTo(4);
        assertThat(context.keptMessages()).hasSize(2);
    }
}
