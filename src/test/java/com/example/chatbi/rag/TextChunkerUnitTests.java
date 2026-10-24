package com.example.chatbi.rag;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class TextChunkerUnitTests {

    private final TextChunker chunker = new TextChunker();

    @Test
    void nullAndBlankProduceNoChunks() {
        assertThat(chunker.chunk(null)).isEmpty();
        assertThat(chunker.chunk("   \n\n  ")).isEmpty();
    }

    @Test
    void shortParagraphsMergeIntoOneChunk() {
        List<String> chunks = chunker.chunk("第一段。\n\n第二段。");

        assertThat(chunks).hasSize(1);
        assertThat(chunks.getFirst()).contains("第一段。").contains("第二段。");
    }

    @Test
    void paragraphsSplitWhenPackingWouldOverflow() {
        String content = "a".repeat(300) + "\n\n" + "b".repeat(300);

        List<String> chunks = chunker.chunk(content);

        assertThat(chunks).hasSize(2);
        assertThat(chunks.get(0)).startsWith("a");
        assertThat(chunks.get(1)).startsWith("b");
    }

    @Test
    void customParamsBoundAndOverlap() {
        TextChunker small = new TextChunker(50, 10);
        List<String> chunks = small.chunk("x".repeat(120));

        assertThat(chunks.size()).isGreaterThanOrEqualTo(3);
        assertThat(chunks).allMatch(chunk -> chunk.length() <= 50);
        assertThat(chunks.get(1)).startsWith(chunks.get(0).substring(40));
    }

    @Test
    void crlfParagraphBreaksAreRecognized() {
        List<String> chunks = chunker.chunk("第一段。\r\n\r\n第二段。");

        assertThat(chunks).hasSize(1);
        assertThat(chunks.getFirst()).contains("第一段。").contains("第二段。");
    }
}
