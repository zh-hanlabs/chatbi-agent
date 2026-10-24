package com.example.chatbi.llm;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * OpenAI 兼容网关配置。api-key 为空即视为未启用,所有 LLM 能力回退本地实现。
 * 默认指向智谱开放平台,可经 chatbi.llm.* 或 CHATBI_LLM_* 环境变量覆盖。
 */
@ConfigurationProperties(prefix = "chatbi.llm")
public record LlmProperties(String baseUrl, String apiKey, String chatModel, String embeddingModel,
                             int timeoutSeconds) {

    public LlmProperties {
        if (baseUrl == null || baseUrl.isBlank()) {
            baseUrl = "https://open.bigmodel.cn/api/paas/v4";
        }
        if (apiKey == null) {
            apiKey = "";
        }
        if (chatModel == null || chatModel.isBlank()) {
            chatModel = "glm-4-flash";
        }
        if (embeddingModel == null || embeddingModel.isBlank()) {
            embeddingModel = "embedding-3";
        }
        if (timeoutSeconds <= 0) {
            timeoutSeconds = 10;
        }
    }

    public boolean enabled() {
        return !apiKey.isBlank();
    }
}
