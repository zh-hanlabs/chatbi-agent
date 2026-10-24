package com.example.chatbi.rag;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

class MockEmbeddingClientUnitTests {

    private final MockEmbeddingClient client = new MockEmbeddingClient();

    @Test
    void dimensionsAreFixed() {
        assertThat(client.dimensions()).isEqualTo(128);
        assertThat(client.embed("任意文本")).hasSize(128);
    }

    @Test
    void emptyTextYieldsZeroVector() {
        assertThat(client.embed("")).containsOnly(0.0f);
        assertThat(client.embed(null)).containsOnly(0.0f);
    }

    @Test
    void sameTextSameVector() {
        assertThat(client.embed("GMV 口径")).containsExactly(client.embed("GMV 口径"));
    }

    @Test
    void latinCaseIsNormalized() {
        assertThat(client.embed("gmv")).containsExactly(client.embed("GMV"));
    }

    @Test
    void nonEmptyVectorIsUnitNorm() {
        float[] vector = client.embed("北京 上海 广州");

        double norm = 0;
        for (float v : vector) {
            norm += (double) v * v;
        }
        assertThat(Math.sqrt(norm)).isCloseTo(1.0, within(1e-5));
    }

    @Test
    void differentTextDifferentVector() {
        assertThat(client.embed("北京")).isNotEqualTo(client.embed("上海"));
    }
}
