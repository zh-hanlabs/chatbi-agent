package com.example.chatbi.llm;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Map;

/**
 * OpenAI 兼容网关客户端(/chat/completions 与 /embeddings)。
 * 任何失败(网络/非 200/结构不符)抛 LlmUnavailableException,由门面决定回退。
 */
@Component
public class OpenAiCompatChatModel {

    public static class LlmUnavailableException extends RuntimeException {
        public LlmUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }

        public LlmUnavailableException(String message) {
            super(message);
        }
    }

    private static final Logger log = LoggerFactory.getLogger(OpenAiCompatChatModel.class);

    private final RestClient restClient;
    private final LlmProperties properties;
    private final ObjectMapper objectMapper;

    public OpenAiCompatChatModel(RestClient llmRestClient, LlmProperties properties, ObjectMapper objectMapper) {
        this.restClient = llmRestClient;
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    public String complete(String systemPrompt, String userPrompt) {
        Map<String, Object> body = Map.of(
                "model", properties.chatModel(),
                "messages", List.of(
                        Map.of("role", "system", "content", systemPrompt),
                        Map.of("role", "user", "content", userPrompt)),
                "temperature", 0);
        try {
            String raw = restClient.post()
                    .uri("/chat/completions")
                    .body(body)
                    .retrieve()
                    .body(String.class);
            ChatCompletionResponse response = objectMapper.readValue(raw == null ? "" : raw,
                    ChatCompletionResponse.class);
            if (response.choices() == null || response.choices().isEmpty()
                    || response.choices().getFirst().message() == null
                    || response.choices().getFirst().message().content() == null) {
                throw new LlmUnavailableException("chat/completions 响应缺少 choices");
            }
            return response.choices().getFirst().message().content();
        } catch (LlmUnavailableException e) {
            throw e;
        } catch (Exception e) {
            log.warn("LLM chat 调用失败: {}", e.getMessage());
            throw new LlmUnavailableException("LLM chat 调用失败", e);
        }
    }

    public float[] embed(String text) {
        Map<String, Object> body = Map.of(
                "model", properties.embeddingModel(),
                "input", text);
        try {
            String raw = restClient.post()
                    .uri("/embeddings")
                    .body(body)
                    .retrieve()
                    .body(String.class);
            EmbeddingResponse response = objectMapper.readValue(raw == null ? "" : raw, EmbeddingResponse.class);
            if (response.data() == null || response.data().isEmpty() || response.data().getFirst().embedding() == null) {
                throw new LlmUnavailableException("embeddings 响应缺少 data");
            }
            List<Double> vector = response.data().getFirst().embedding();
            float[] result = new float[vector.size()];
            for (int i = 0; i < vector.size(); i++) {
                result[i] = vector.get(i).floatValue();
            }
            return result;
        } catch (LlmUnavailableException e) {
            throw e;
        } catch (Exception e) {
            log.warn("LLM embeddings 调用失败: {}", e.getMessage());
            throw new LlmUnavailableException("LLM embeddings 调用失败", e);
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record ChatCompletionResponse(List<Choice> choices) {
        @JsonIgnoreProperties(ignoreUnknown = true)
        record Choice(Message message) {
            @JsonIgnoreProperties(ignoreUnknown = true)
            record Message(String content) {
            }
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record EmbeddingResponse(List<Item> data) {
        @JsonIgnoreProperties(ignoreUnknown = true)
        record Item(List<Double> embedding) {
        }
    }
}
