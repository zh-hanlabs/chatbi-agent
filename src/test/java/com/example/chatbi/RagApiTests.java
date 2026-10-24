package com.example.chatbi;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class RagApiTests {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void cleanKnowledgeBase() {
        jdbcTemplate.update("DELETE FROM document_chunks");
        jdbcTemplate.update("DELETE FROM documents");
    }

    private void upload(String title, String content) throws Exception {
        mockMvc.perform(post("/api/documents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"%s\",\"content\":%s}".formatted(title, json(content))))
                .andExpect(status().isCreated());
    }

    @Test
    void knowledgeQuestionRoutesToRagWithCitations() throws Exception {
        upload("业务口径说明", "GMV 的口径是已完成订单的金额总和。");

        mockMvc.perform(post("/api/rag/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":3,\"question\":\"GMV 口径指的是什么\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.route").value("RAG"))
                .andExpect(jsonPath("$.answer").value("GMV 的口径是已完成订单的金额总和。"))
                .andExpect(jsonPath("$.citations[0].documentTitle").value("业务口径说明"))
                .andExpect(jsonPath("$.citations[0].chunkIndex").value(0))
                .andExpect(jsonPath("$.citations[0].score").isNumber());
    }

    @Test
    void metricQuestionRoutesToNl2sql() throws Exception {
        mockMvc.perform(post("/api/rag/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":3,\"question\":\"北京上个月的 GMV 是多少\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.route").value("NL2SQL"))
                .andExpect(jsonPath("$.sql.metric").value("GMV"))
                .andExpect(jsonPath("$.sql.sql").isNotEmpty());
    }

    @Test
    void offDomainQuestionIsRefused() throws Exception {
        upload("业务口径说明", "GMV 的口径是已完成订单的金额总和。");

        mockMvc.perform(post("/api/rag/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":3,\"question\":\"隔壁食堂今天中午有什么菜\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.route").value("REFUSED"))
                .andExpect(jsonPath("$.answer").isNotEmpty())
                .andExpect(jsonPath("$.citations").isEmpty());
    }

    @Test
    void emptyKnowledgeBaseRefuses() throws Exception {
        mockMvc.perform(post("/api/rag/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":3,\"question\":\"GMV 口径指的是什么\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.route").value("REFUSED"));
    }

    @Test
    void retrieveReturnsTopKWithScores() throws Exception {
        upload("GMV 口径", "GMV 的口径是已完成订单的金额总和。");
        upload("退款口径", "退款率是退款订单占总订单的比例。");

        mockMvc.perform(post("/api/rag/retrieve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":3,\"question\":\"退款率的定义\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].content").value("退款率是退款订单占总订单的比例。"))
                .andExpect(jsonPath("$[0].documentTitle").value("退款口径"))
                .andExpect(jsonPath("$[0].score").isNumber());
    }

    @Test
    void conversationChatRoutesKnowledgeQuestionToCitedAnswer() throws Exception {
        upload("业务口径说明", "GMV 的口径是已完成订单的金额总和。");

        String conversationId = createConversation(1);
        mockMvc.perform(post("/api/conversations/{id}/chat", conversationId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"question\":\"GMV 口径指的是什么\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.answer").value("GMV 的口径是已完成订单的金额总和。"))
                .andExpect(jsonPath("$.requiresTool").value(false));

        mockMvc.perform(post("/api/conversations/{id}/chat", conversationId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"question\":\"北京近7天订单量\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requiresTool").value(true))
                .andExpect(jsonPath("$.toolCall.name").value("execute_sql"))
                .andExpect(jsonPath("$.toolCall.arguments.sql").isNotEmpty());
    }

    private String createConversation(long userId) throws Exception {
        String response = mockMvc.perform(post("/api/conversations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":%d,\"title\":\"RAG 会话\"}".formatted(userId)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return new com.fasterxml.jackson.databind.ObjectMapper().readTree(response).get("id").asText();
    }

    private String json(String value) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(value);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
