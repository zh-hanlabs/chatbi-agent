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

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * REQ-002 权限执行:种子权限为
 * user1=北京分析师(北京, GMV/ORDER_COUNT)、user2=上海分析师(上海, GMV/REFUND_RATE)、
 * user3=管理员(全部区域, 全部指标)。
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class PermissionEnforcementApiTests {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void cleanState() {
        jdbcTemplate.update("DELETE FROM audit_logs");
        jdbcTemplate.update("DELETE FROM document_chunks");
        jdbcTemplate.update("DELETE FROM documents");
    }

    @Test
    void permissionsEndpointReturnsSeedGrants() throws Exception {
        mockMvc.perform(get("/api/users/1/permissions"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value(1))
                .andExpect(jsonPath("$.regions[0]").value("北京"))
                .andExpect(jsonPath("$.metrics.length()").value(2));

        mockMvc.perform(get("/api/users/3/permissions"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.regions.length()").value(3))
                .andExpect(jsonPath("$.metrics.length()").value(3));

        mockMvc.perform(get("/api/users/999/permissions"))
                .andExpect(status().isNotFound());
    }

    @Test
    void nl2sqlRejectsForeignRegionWith403() throws Exception {
        mockMvc.perform(post("/api/nl2sql")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"question\":\"上海的 GMV 是多少\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error").value("无 上海 区域的查询权限"));
    }

    @Test
    void nl2sqlRejectsUngrantedMetricWith403() throws Exception {
        mockMvc.perform(post("/api/nl2sql")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"question\":\"北京的退款率\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error").value("无 REFUND_RATE 指标的查询权限"));
    }

    @Test
    void nl2sqlAllowsGrantedCombination() throws Exception {
        mockMvc.perform(post("/api/nl2sql")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"question\":\"北京的 GMV\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.metric").value("GMV"));
    }

    @Test
    void ragQueryRejectsForeignRegionOnNl2sqlRoute() throws Exception {
        mockMvc.perform(post("/api/rag/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":2,\"question\":\"广州近7天订单量\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void ragQueryKnowledgeRouteIgnoresPermissions() throws Exception {
        // 语料自给自足,不依赖其他测试类的执行顺序
        upload("业务口径说明", "GMV 的口径是已完成订单的金额总和。");

        // 口径文档全员可读,知识问题不受数据权限影响
        mockMvc.perform(post("/api/rag/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"question\":\"GMV 的口径是什么\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.route").value("RAG"));
    }

    @Test
    void confirmRejectsForeignRegionInSqlWith422() throws Exception {
        mockMvc.perform(post("/api/sql/confirm")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"sql\":\"SELECT COUNT(*) AS c FROM orders o "
                                + "JOIN regions r ON r.id = o.region_id WHERE r.name = '上海'\"}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error").value("无 上海 区域的查询权限"));

        // 拒绝落审计
        mockMvc.perform(get("/api/audit").param("userId", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].allowed").value(false))
                .andExpect(jsonPath("$[0].reason").value("PERMISSION_DENIED: 无 上海 区域的查询权限"));
    }

    @Test
    void confirmAllowsGrantedRegion() throws Exception {
        mockMvc.perform(post("/api/sql/confirm")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"sql\":\"SELECT COUNT(*) AS c FROM orders o "
                                + "JOIN regions r ON r.id = o.region_id WHERE r.name = '北京'\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.rowCount").value(1));
    }

    @Test
    void chatRejectsUngrantedMetricAndAudits() throws Exception {
        String conversationId = createConversation(1);
        mockMvc.perform(post("/api/conversations/{id}/chat", conversationId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"question\":\"北京的退款率是多少\"}"))
                .andExpect(status().isForbidden());

        mockMvc.perform(get("/api/audit").param("userId", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].action").value("CHAT"))
                .andExpect(jsonPath("$[0].allowed").value(false))
                .andExpect(jsonPath("$[0].reason").value("PERMISSION_DENIED: 无 REFUND_RATE 指标的查询权限"));
    }

    @Test
    void chatAllowsGrantedMetric() throws Exception {
        String conversationId = createConversation(1);
        mockMvc.perform(post("/api/conversations/{id}/chat", conversationId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"question\":\"北京近7天订单量\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requiresTool").value(true));
    }

    @Test
    void adminPassesAllCombinations() throws Exception {
        for (String question : List.of("北京的 GMV", "上海的退款率", "广州的订单量", "总订单量")) {
            mockMvc.perform(post("/api/nl2sql")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{\"userId\":3,\"question\":\"%s\"}".formatted(question)))
                    .andExpect(status().isOk());
        }
    }

    private void upload(String title, String content) throws Exception {
        mockMvc.perform(post("/api/documents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"%s\",\"content\":\"%s\"}".formatted(title, content)))
                .andExpect(status().isCreated());
    }

    private String createConversation(long userId) throws Exception {
        String response = mockMvc.perform(post("/api/conversations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":%d,\"title\":\"权限会话\"}".formatted(userId)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return new com.fasterxml.jackson.databind.ObjectMapper().readTree(response).get("id").asText();
    }

    private static final class List {
        static java.util.List<String> of(String... items) {
            return java.util.List.of(items);
        }
    }
}
