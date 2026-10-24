package com.example.chatbi.llm;

import com.example.chatbi.rag.EmbeddingClient;
import com.example.chatbi.rag.MockEmbeddingClient;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class EmbeddingClientDelegateTests {

    private final EmbeddingClient mockClient = new MockEmbeddingClient();

    private EmbeddingClientDelegate delegate(OpenAiCompatChatModel model, boolean enabled) {
        return new EmbeddingClientDelegate(mockClient, model,
                new LlmProperties("http://x", enabled ? "key" : "", "m", "e", 5));
    }

    @Test
    void disabledKeyUsesMockVectors() {
        EmbeddingClientDelegate delegate = delegate(mock(OpenAiCompatChatModel.class), false);

        assertThat(delegate.embed("GMV")).containsExactly(mockClient.embed("GMV"));
    }

    @Test
    void enabledKeyUsesGatewayAndCaches() {
        OpenAiCompatChatModel model = mock(OpenAiCompatChatModel.class);
        float[] remote = {0.1f, 0.2f};
        when(model.embed(anyString())).thenReturn(remote);
        EmbeddingClientDelegate delegate = delegate(model, true);

        assertThat(delegate.embed("GMV")).containsExactly(remote);
        assertThat(delegate.embed("GMV")).containsExactly(remote);
        // 第二次命中缓存,网关只调了一次
        verify(model, times(1)).embed("GMV");
    }

    @Test
    void gatewayFailureFallsBackToMock() {
        OpenAiCompatChatModel model = mock(OpenAiCompatChatModel.class);
        when(model.embed(anyString()))
                .thenThrow(new OpenAiCompatChatModel.LlmUnavailableException("timeout"));
        EmbeddingClientDelegate delegate = delegate(model, true);

        assertThat(delegate.embed("GMV")).containsExactly(mockClient.embed("GMV"));
    }

    @Test
    void mockFailureWhenDisabledIsNotSwallowed() {
        EmbeddingClient broken = Mockito.mock(EmbeddingClient.class);
        when(broken.embed(anyString())).thenThrow(new IllegalStateException("mock broken"));
        EmbeddingClientDelegate delegate = new EmbeddingClientDelegate(broken,
                mock(OpenAiCompatChatModel.class), new LlmProperties("http://x", "", "m", "e", 5));

        // 未启用 LLM 时本地实现异常应如实抛出,不静默吞掉
        assertThatThrownBy(() -> delegate.embed("GMV"))
                .isInstanceOf(IllegalStateException.class);
    }
}
