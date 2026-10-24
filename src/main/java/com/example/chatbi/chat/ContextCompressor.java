package com.example.chatbi.chat;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 多轮上下文压缩:历史不超过阈值时原样保留;超过后把较早的消息
 * 折叠成一句摘要,仅保留最近几轮原文,保证提示词长度有界。
 */
@Component
public class ContextCompressor {

    public record CompressedContext(String summary, List<ChatMessage> keptMessages, int droppedCount,
                                    int totalMessages) {

        @com.fasterxml.jackson.annotation.JsonProperty("compressed")
        public boolean compressed() {
            return droppedCount > 0;
        }
    }

    private final Summarizer summarizer;
    private final int compressThreshold;
    private final int keepRecent;

    public ContextCompressor(Summarizer summarizer,
            @Value("${chatbi.context.compress-threshold:10}") int compressThreshold,
            @Value("${chatbi.context.keep-recent:6}") int keepRecent) {
        this.summarizer = summarizer;
        this.compressThreshold = compressThreshold;
        this.keepRecent = keepRecent;
    }

    public CompressedContext compress(List<ChatMessage> messages) {
        if (messages.size() <= compressThreshold) {
            return new CompressedContext(null, messages, 0, messages.size());
        }
        List<ChatMessage> dropped = messages.subList(0, messages.size() - keepRecent);
        List<ChatMessage> kept = messages.subList(messages.size() - keepRecent, messages.size());
        return new CompressedContext(summarizer.summarize(dropped), kept, dropped.size(), messages.size());
    }
}
