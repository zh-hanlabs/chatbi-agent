package com.example.chatbi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ContextCompressionApiTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shortHistoryStaysVerbatim() throws Exception {
        String conversationId = createConversation(1);
        chat(conversationId, 1, "北京近7天订单量");

        mockMvc.perform(get("/api/conversations/{id}/context", conversationId).param("userId", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.compressed").value(false))
                .andExpect(jsonPath("$.droppedCount").value(0))
                .andExpect(jsonPath("$.summary").isEmpty())
                .andExpect(jsonPath("$.totalMessages").value(2))
                .andExpect(jsonPath("$.keptMessages.length()").value(2));
    }

    @Test
    void longHistoryIsCompressedIntoSummaryPlusRecent() throws Exception {
        String conversationId = createConversation(1);
        for (int i = 1; i <= 6; i++) {
            chat(conversationId, 1, "北京近" + i + "天订单量");
        }

        mockMvc.perform(get("/api/conversations/{id}/context", conversationId).param("userId", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.compressed").value(true))
                .andExpect(jsonPath("$.totalMessages").value(12))
                .andExpect(jsonPath("$.droppedCount").value(6))
                .andExpect(jsonPath("$.keptMessages.length()").value(6))
                .andExpect(jsonPath("$.summary").value(
                        "此前对话共 3 次提问,主要问题: 北京近1天订单量 / 北京近2天订单量 / 北京近3天订单量;其间生成过 3 次查询工具调用。"));
    }

    @Test
    void summaryMentionsToolCallCount() throws Exception {
        String conversationId = createConversation(1);
        for (int i = 1; i <= 6; i++) {
            chat(conversationId, 1, "上海近" + i + "天GMV");
        }

        mockMvc.perform(get("/api/conversations/{id}/context", conversationId).param("userId", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.summary").value(
                        "此前对话共 3 次提问,主要问题: 上海近1天GMV / 上海近2天GMV / 上海近3天GMV;其间生成过 3 次查询工具调用。"));
    }

    @Test
    void contextIsIsolatedPerUser() throws Exception {
        String conversationId = createConversation(1);
        chat(conversationId, 1, "北京近7天订单量");

        mockMvc.perform(get("/api/conversations/{id}/context", conversationId).param("userId", "2"))
                .andExpect(status().isNotFound());
    }

    private String createConversation(long userId) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/conversations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":%d,\"title\":\"压缩会话\"}".formatted(userId)))
                .andExpect(status().isCreated())
                .andReturn();
        return new com.fasterxml.jackson.databind.ObjectMapper()
                .readTree(result.getResponse().getContentAsString()).get("id").asText();
    }

    private void chat(String conversationId, long userId, String question) throws Exception {
        mockMvc.perform(post("/api/conversations/{id}/chat", conversationId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":%d,\"question\":\"%s\"}".formatted(userId, question)))
                .andExpect(status().isOk());
    }
}
