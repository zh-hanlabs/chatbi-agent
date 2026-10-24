package com.example.chatbi;

import com.example.chatbi.nl2sql.SqlGenerator;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class CacheAuditApiTests {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private SqlGenerator sqlGenerator;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void cleanAuditLog() {
        jdbcTemplate.update("DELETE FROM audit_logs");
    }

    @Test
    void repeatedConfirmServedFromCache() throws Exception {
        String sql = sqlGenerator.generate("北京的 GMV").sql();
        String body = "{\"userId\":3,\"sql\":%s}".formatted(json(sql));

        mockMvc.perform(post("/api/sql/confirm").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.cacheHit").value(false))
                .andExpect(jsonPath("$.rows[0].gmv").value(1098.0));

        mockMvc.perform(post("/api/sql/confirm").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.cacheHit").value(true))
                .andExpect(jsonPath("$.rows[0].gmv").value(1098.0));
    }

    @Test
    void cacheIsScopedPerUser() throws Exception {
        String sql = sqlGenerator.generate("总订单量").sql();
        mockMvc.perform(post("/api/sql/confirm")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"sql\":%s}".formatted(json(sql))))
                .andExpect(jsonPath("$.cacheHit").value(false));

        mockMvc.perform(post("/api/sql/confirm")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":3,\"sql\":%s}".formatted(json(sql))))
                .andExpect(jsonPath("$.cacheHit").value(false));
    }

    @Test
    void executedConfirmIsAudited() throws Exception {
        String sql = sqlGenerator.generate("上海的 GMV").sql();
        mockMvc.perform(post("/api/sql/confirm")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":2,\"conversationId\":null,\"sql\":%s}".formatted(json(sql))))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/audit").param("userId", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].action").value("SQL_CONFIRM"))
                .andExpect(jsonPath("$[0].userId").value(2))
                .andExpect(jsonPath("$[0].allowed").value(true))
                .andExpect(jsonPath("$[0].reason").value("executed"))
                .andExpect(jsonPath("$[0].generatedSql").value(sql));
    }

    @Test
    void rejectedConfirmIsAudited() throws Exception {
        mockMvc.perform(post("/api/sql/confirm")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"sql\":\"DELETE FROM orders\"}"))
                .andExpect(status().isUnprocessableEntity());

        mockMvc.perform(get("/api/audit").param("userId", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].action").value("SQL_CONFIRM"))
                .andExpect(jsonPath("$[0].allowed").value(false))
                .andExpect(jsonPath("$[0].reason").isNotEmpty());
    }

    @Test
    void cacheHitIsAudited() throws Exception {
        String sql = sqlGenerator.generate("广州的退款率").sql();
        String body = "{\"userId\":3,\"sql\":%s}".formatted(json(sql));
        mockMvc.perform(post("/api/sql/confirm").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/sql/confirm").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(jsonPath("$.cacheHit").value(true));

        mockMvc.perform(get("/api/audit").param("userId", "3").param("limit", "10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].reason").value("cache_hit"))
                .andExpect(jsonPath("$[1].reason").value("executed"));
    }

    @Test
    void chatIsAuditedWithConversationId() throws Exception {
        String conversationId = createConversation(1);
        mockMvc.perform(post("/api/conversations/{id}/chat", conversationId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"question\":\"GMV 的口径是什么\"}"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/audit").param("userId", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].action").value("CHAT"))
                .andExpect(jsonPath("$[0].conversationId").value(conversationId))
                .andExpect(jsonPath("$[0].question").value("GMV 的口径是什么"))
                .andExpect(jsonPath("$[0].allowed").value(true));
    }

    @Test
    void auditEndpointRejectsNonAdmin() throws Exception {
        mockMvc.perform(get("/api/audit").param("userId", "1"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void confirmWithoutUserIdIsRejected() throws Exception {
        mockMvc.perform(post("/api/sql/confirm")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sql\":\"SELECT COUNT(*) AS c FROM orders\"}"))
                .andExpect(status().isBadRequest());
    }

    private String createConversation(long userId) throws Exception {
        String response = mockMvc.perform(post("/api/conversations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":%d,\"title\":\"审计会话\"}".formatted(userId)))
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
