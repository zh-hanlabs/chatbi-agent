package com.example.chatbi;

import com.example.chatbi.rag.EmbeddingClient;
import com.example.chatbi.rag.TextChunker;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Arrays;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class DocumentPipelineApiTests {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private TextChunker chunker;

    @Autowired
    private EmbeddingClient embeddingClient;

    @BeforeEach
    void cleanDocuments() {
        jdbcTemplate.update("DELETE FROM document_chunks");
        jdbcTemplate.update("DELETE FROM documents");
    }

    @Test
    void uploadSplitsAndPersistsChunks() throws Exception {
        String content = "GMV 的口径是已完成订单的金额总和。\n\n退款率按退款订单数除以总订单数计算。\n\n"
                + "北京区域覆盖华北市场,重点关注大客户订单。";
        mockMvc.perform(post("/api/documents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"业务口径说明\",\"content\":%s}".formatted(json(content))))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.documentId").isNumber())
                .andExpect(jsonPath("$.title").value("业务口径说明"))
                .andExpect(jsonPath("$.chunkCount").isNumber());

        Integer chunks = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL", Integer.class);
        assertThat(chunks).isGreaterThanOrEqualTo(1);
    }

    @Test
    void chunksKeepOriginalText() throws Exception {
        String content = "退款率按退款订单数除以总订单数计算。";
        String response = mockMvc.perform(post("/api/documents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"口径\",\"content\":%s}".formatted(json(content))))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        long documentId = new com.fasterxml.jackson.databind.ObjectMapper()
                .readTree(response).get("documentId").asLong();

        mockMvc.perform(get("/api/documents/{id}/chunks", documentId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].chunkIndex").value(0))
                .andExpect(jsonPath("$[0].content").value(content))
                .andExpect(jsonPath("$[0].embedding").isNotEmpty());
    }

    @Test
    void longDocumentIsSplitWithinSizeBound() {
        String paragraph = "a".repeat(1200);
        var chunks = chunker.chunk(paragraph);

        assertThat(chunks.size()).isGreaterThanOrEqualTo(3);
        assertThat(chunks).allMatch(chunk -> chunk.length() <= TextChunker.TARGET_CHUNK_SIZE);
        // 相邻块保留重叠,跨块语义不断裂
        assertThat(chunks.get(1)).startsWith(chunks.get(0)
                .substring(chunks.get(0).length() - TextChunker.OVERLAP_SIZE));
    }

    @Test
    void listAndDetailEndpointsWork() throws Exception {
        String content = "北京区域覆盖华北市场。";
        String response = mockMvc.perform(post("/api/documents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"区域说明\",\"content\":%s}".formatted(json(content))))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        long documentId = new com.fasterxml.jackson.databind.ObjectMapper()
                .readTree(response).get("documentId").asLong();

        mockMvc.perform(get("/api/documents"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(documentId))
                .andExpect(jsonPath("$[0].title").value("区域说明"));

        mockMvc.perform(get("/api/documents/{id}", documentId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(documentId));

        mockMvc.perform(get("/api/documents/999"))
                .andExpect(status().isNotFound());
    }

    @Test
    void embeddingIsDeterministicAndSimilarTextRanksHigher() {
        float[] gmv = embeddingClient.embed("GMV 是已完成订单的金额总和");
        float[] gmvAgain = embeddingClient.embed("GMV 是已完成订单的金额总和");
        float[] refund = embeddingClient.embed("退款率是退款订单占总订单的比例");

        assertThat(gmv).containsExactly(gmvAgain);
        assertThat(cosine(gmv, refund)).isLessThan(1.0);
        assertThat(cosine(gmv, embeddingClient.embed("GMV 就是已完成订单的金额总和")))
                .isGreaterThan(cosine(gmv, refund));
    }

    @Test
    void blankUploadIsRejected() throws Exception {
        mockMvc.perform(post("/api/documents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\" \",\"content\":\"x\"}"))
                .andExpect(status().isBadRequest());
    }

    private double cosine(float[] a, float[] b) {
        double dot = 0;
        for (int i = 0; i < a.length; i++) {
            dot += (double) a[i] * b[i];
        }
        return dot;
    }

    private String json(String value) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(value);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
