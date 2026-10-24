package com.example.chatbi.llm;

import com.example.chatbi.rag.EmbeddingClient;
import com.example.chatbi.rag.MockEmbeddingClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

/**
 * EmbeddingClient 门面:配置 Key 走网关 embeddings(同文本结果缓存),
 * 失败/未配置回退确定性哈希实现。
 * 注意:两种向量空间不兼容,切换实现后需重新向量化已有文档。
 */
@Component
@Primary
public class EmbeddingClientDelegate implements EmbeddingClient {

    private static final Logger log = LoggerFactory.getLogger(EmbeddingClientDelegate.class);

    private static final int CACHE_LIMIT = 10_000;

    private final EmbeddingClient mock;
    private final OpenAiCompatChatModel chatModel;
    private final LlmProperties properties;
    private final java.util.concurrent.ConcurrentHashMap<String, float[]> cache =
            new java.util.concurrent.ConcurrentHashMap<>();

    public EmbeddingClientDelegate(@Qualifier("mockEmbeddingClient") EmbeddingClient mock,
            OpenAiCompatChatModel chatModel, LlmProperties properties) {
        this.mock = mock;
        this.chatModel = chatModel;
        this.properties = properties;
    }

    @Override
    public int dimensions() {
        return MockEmbeddingClient.DIMENSIONS;
    }

    @Override
    public float[] embed(String text) {
        if (!properties.enabled()) {
            return mock.embed(text);
        }
        float[] cached = cache.get(text);
        if (cached != null) {
            return cached;
        }
        try {
            float[] vector = chatModel.embed(text);
            if (cache.size() >= CACHE_LIMIT) {
                cache.clear();
            }
            cache.put(text, vector);
            return vector;
        } catch (Exception e) {
            log.warn("LLM embeddings 失败,回退哈希实现: {}", e.getMessage());
            return mock.embed(text);
        }
    }
}
